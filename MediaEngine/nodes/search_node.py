"""
Search node implementation
Responsible for generating search queries and reflection queries
"""

import json
from typing import Dict, Any
from json.decoder import JSONDecodeError
from loguru import logger

from .base_node import BaseNode
from ..prompts import SYSTEM_PROMPT_FIRST_SEARCH, SYSTEM_PROMPT_REFLECTION
from ..utils.text_processing import (
    remove_reasoning_from_output,
    clean_json_tags,
    extract_clean_response,
    fix_incomplete_json
)
from utils.agent_helpers import parse_search_node_output


class FirstSearchNode(BaseNode):
    """Node that generates the first search query for the paragraph"""
    
    def __init__(self, llm_client):
        """
        Initialize the first search node
        
        Args:
            llm_client: LLM client
        """
        super().__init__(llm_client, "FirstSearchNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                return "title" in data and "content" in data
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            return "title" in input_data and "content" in input_data
        return False
    
    def run(self, input_data: Any, **kwargs) -> Dict[str, str]:
        """
        Call LLM to generate search query and justification
        
        Args:
            input_data: string or dictionary containing title and content
            **kwargs: extra parameters
            
        Returns:
            Dictionary containing search_query and reasoning
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("Input data format error，Need to include title and content fields")
            

            if isinstance(input_data, str):
                message = input_data
            else:
                message = json.dumps(input_data, ensure_ascii=False)
            
            logger.info("Generating first search query")
            

            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_FIRST_SEARCH, message)
            

            processed_response = self.process_output(response)
            
            logger.info(f"Generate search query: {processed_response.get('search_query', 'N/A')}")
            return processed_response
            
        except Exception as e:
            logger.exception(f"Failed to generate first search query: {str(e)}")
            raise e
    
    def process_output(self, output: str) -> Dict[str, Any]:
        """Process LLM output, extracting search query, reasoning, and optional search parameters."""
        return parse_search_node_output(
            output,
            remove_reasoning_fn=remove_reasoning_from_output,
            clean_json_tags_fn=clean_json_tags,
            extract_clean_response_fn=extract_clean_response,
            fix_incomplete_json_fn=fix_incomplete_json,
            default_fn=self._get_default_search_query,
        )
    
    def _get_default_search_query(self) -> Dict[str, str]:
        """
        Get default search query
        
        Returns:
            Default search query dictionary
        """
        return {
            "search_query": "Research on related topics",
            "reasoning": "due to parsing failure，Use default search query"
        }


class ReflectionNode(BaseNode):
    """Nodes that reflect on paragraphs and generate new search queries"""
    
    def __init__(self, llm_client):
        """
        Initialize reflection node
        
        Args:
            llm_client: LLM client
        """
        super().__init__(llm_client, "ReflectionNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "paragraph_latest_state"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "paragraph_latest_state"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> Dict[str, str]:
        """
        Call LLM to reflect and generate search queries
        
        Args:
            input_data: containstitle、contentand a string or dictionary of paragraph_latest_state
            **kwargs: extra parameters
            
        Returns:
            Dictionary containing search_query and reasoning
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("Input data format error，need to includetitle、contentand paragraph_latest_state field")
            

            if isinstance(input_data, str):
                message = input_data
            else:
                message = json.dumps(input_data, ensure_ascii=False)
            
            logger.info("Reflection in progress and new search query generated")
            

            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_REFLECTION, message)
            

            processed_response = self.process_output(response)
            
            logger.info(f"Reflection on generating search queries: {processed_response.get('search_query', 'N/A')}")
            return processed_response
            
        except Exception as e:
            logger.exception(f"Reflection failed to generate search query: {str(e)}")
            raise e
    
    def process_output(self, output: str) -> Dict[str, Any]:
        """Process LLM output, extracting reflection search query, reasoning, and optional parameters."""
        return parse_search_node_output(
            output,
            remove_reasoning_fn=remove_reasoning_from_output,
            clean_json_tags_fn=clean_json_tags,
            extract_clean_response_fn=extract_clean_response,
            fix_incomplete_json_fn=fix_incomplete_json,
            default_fn=self._get_default_reflection_query,
        )
    
    def _get_default_reflection_query(self) -> Dict[str, str]:
        """
        Get the default reflection search query
        
        Returns:
            Default reflective search query dictionary
        """
        return {
            "search_query": "Additional information for in-depth research",
            "reasoning": "due to parsing failure，Use default reflection search query"
        }
