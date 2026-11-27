"""
Template selection node。

Comprehensive user query、tri-engine report、Forum log and local template library,
Call LLM to select the most appropriate report skeleton。
"""

import os
import json
from typing import Dict, Any, List, Optional
from loguru import logger

from .base_node import BaseNode
from ..prompts import SYSTEM_PROMPT_TEMPLATE_SELECTION
from ..utils.json_parser import RobustJSONParser, JSONParseError


class TemplateSelectionNode(BaseNode):
    """
    Template selection processing node.

    Responsible for preparing template candidate list、Build prompt words、Parsing LLM returns results,
    and fall back to built-in templates on failure。
    """
    
    def __init__(self, llm_client, template_dir: str = "ReportEngine/report_template"):
        """
        initializationTemplate selection node

        Args:
            llm_client: LLMclient
            template_dir: Template directory path
        """
        super().__init__(llm_client, "TemplateSelectionNode")
        self.template_dir = template_dir

        self.json_parser = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,
            max_repair_attempts=3,
        )
        
    def run(self, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Perform template selection。
        
        Args:
            input_data: Dictionary containing query and report content
                - query: original query
                - reports: Report list of three sub-agents
                - forum_logs: Forum log content
                
        Returns:
            Selected template information, including name、Contents and reasons for selection
        """
        logger.info("Starting template selection...")
        
        query = input_data.get('query', '')
        reports = input_data.get('reports', [])
        forum_logs = input_data.get('forum_logs', '')
        

        available_templates = self._get_available_templates()
        
        if not available_templates:
            logger.info("No preset template found, using built-in default template")
            return self._get_fallback_template()
        

        try:
            llm_result = self._llm_template_selection(query, reports, forum_logs, available_templates)
            if llm_result:
                return llm_result
        except Exception as e:
            logger.exception(f"LLM template selection failed: {str(e)}")
        

        return self._get_fallback_template()
    

    
    def _llm_template_selection(self, query: str, reports: List[Any], forum_logs: str, 
                              available_templates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Use LLM for template selection.

        Construct template list and report summary → callLLM → parseJSON →
        Verify that the template exists and return the standard structure.

        parameter:
            query: Keywords entered by the user。
            reports: Report content from multiple analytics engines。
            forum_logs: Forum log, may be empty。
            available_templates: List of locally available templates.

        return:
            dict | None: If LLM successfully returns a legal result, it contains template information, otherwiseNone。
        """
        logger.info("Attempting to use LLM for template selection...")
        

        template_list = "\n".join([f"- {t['name']}: {t['description']}" for t in available_templates])
        

        reports_summary_parts = []
        if reports:
            reports_summary = "\n\n=== Analysis Engine Report Content ===\n"
            for i, report in enumerate(reports, 1):

                if isinstance(report, dict):
                    content = report.get('content', str(report))
                elif hasattr(report, 'content'):
                    content = report.content
                else:
                    content = str(report)
                

                if len(content) > 1000:
                    content = content[:1000] + "...(Content truncated)"
                
                reports_summary_parts.append(f"\nReport {i} content:\n{content}\n")
        

        forum_summary_parts = []
        if forum_logs and forum_logs.strip():
            forum_summary = "\n\n=== Three Engines Discussion Content ===\n"

            if len(forum_logs) > 800:
                forum_content = forum_logs[:800] + "...(Discussion has been truncated)"
            else:
                forum_content = forum_logs
            forum_summary_parts.append(forum_content)
        
        user_message = f"""Query content: {query}

Number of reports: {len(reports)} analytics engine reports
Forum log: {'have' if forum_logs else 'none'}
{reports_summary}{forum_summary}

Available templates:
{template_list}

Please follow the query content、Report content and forum log specifics, choose the most appropriate template。"""
        

        response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_TEMPLATE_SELECTION, user_message)


        if not response or not response.strip():
            logger.error("LLMReturn empty response")
            return None

        logger.info(f"LLMoriginal response: {response}")


        try:
            result = self.json_parser.parse(
                response,
                context_name="Template selection",
                expected_keys=["template_name", "selection_reason"],
            )


            selected_template_name = result.get('template_name', '')
            for template in available_templates:
                if template['name'] == selected_template_name or selected_template_name in template['name']:
                    logger.info(f"LLMSelect template: {selected_template_name}")
                    return {
                        'template_name': template['name'],
                        'template_content': template['content'],
                        'selection_reason': result.get('selection_reason', 'LLMSmart choice')
                    }

            logger.error(f"LLMThe selected template does not exist: {selected_template_name}")
            return None

        except JSONParseError as e:
            logger.error(f"JSONParsing failed: {str(e)}")

            return self._extract_template_from_text(response, available_templates)
    

    def _extract_template_from_text(self, response: str, available_templates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Extract template information from text responses.

        When LLM does not output valid JSON, it tries to downgrade by matching the template name keyword.

        parameter:
            response: Unstructured LLM text。
            available_templates: List of optional templates.

        return:
            dict | None: Returns the template details if the match is successful, otherwiseNone。
        """
        logger.info("Try to extract template information from text response")
        

        for template in available_templates:
            template_name_variants = [
                template['name'],
                template['name'].replace('.md', ''),
                template['name'].replace('template', ''),
            ]
            
            for variant in template_name_variants:
                if variant in response:
                    logger.info(f"Template found in response: {template['name']}")
                    return {
                        'template_name': template['name'],
                        'template_content': template['content'],
                        'selection_reason': 'Extract from text response'
                    }
        
        return None
    
    def _get_available_templates(self) -> List[Dict[str, Any]]:
        """
        Get a list of available templates.

        Enumeration template directory `.md` file and reads the content and description fields.

        return:
            list[dict]: Each item contains name/path/content/description。
        """
        templates = []
        
        if not os.path.exists(self.template_dir):
            logger.error(f"Template directory does not exist: {self.template_dir}")
            return templates
        

        for filename in os.listdir(self.template_dir):
            if filename.endswith('.md'):
                template_path = os.path.join(self.template_dir, filename)
                try:
                    with open(template_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    template_name = filename.replace('.md', '')
                    description = self._extract_template_description(template_name)
                    
                    templates.append({
                        'name': template_name,
                        'path': template_path,
                        'content': content,
                        'description': description
                    })
                except Exception as e:
                    logger.exception(f"Failed to read template file {filename}: {str(e)}")
        
        return templates
    
    def _extract_template_description(self, template_name: str) -> str:
        """Generate a description based on the template name to facilitate LLM's understanding of template positioning。"""
        if 'corporate brand' in template_name:
            return "Suitable for corporate brand reputation and image analysis"
        elif 'market competition' in template_name:
            return "Suitable for market competition landscape and opponent analysis"
        elif 'daily' in template_name or 'regular' in template_name:
            return "Suitable for daily monitoring and regular reporting"
        elif 'policy' in template_name or 'industry' in template_name:
            return "Suitable for policy impact and industry dynamics analysis"
        elif 'Hotspot' in template_name or 'society' in template_name:
            return "Suitable for analysis of social hot spots and public events"
        elif 'sudden' in template_name or 'crisis' in template_name:
            return "Suitable for emergencies and crisis public relations"
        
        return "Generic report template"
    

    
    def _get_fallback_template(self) -> Dict[str, Any]:
        """
        Get an alternate default template (empty template, let LLM do its thing).

        return:
            dict: The structure fields are consistent with LLM returns, making it easy to replace them directly.。
        """
        logger.info("No suitable template found, use empty template to let LLM play its role")
        
        return {
            'template_name': 'Free play template',
            'template_content': '',
            'selection_reason': 'No suitable preset template was found, allowing LLM to design its own report structure based on the content.'
        }
