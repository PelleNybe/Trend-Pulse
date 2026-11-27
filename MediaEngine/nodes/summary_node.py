"""
Summary node implementation
Responsible for generating and updating paragraph content based on search results
"""

import json
from typing import Dict, Any, List
from json.decoder import JSONDecodeError
from loguru import logger

from .base_node import StateMutationNode
from ..state.state import State
from ..prompts import SYSTEM_PROMPT_FIRST_SUMMARY, SYSTEM_PROMPT_REFLECTION_SUMMARY
from ..utils.text_processing import (
    remove_reasoning_from_output,
    clean_json_tags,
    extract_clean_response,
    fix_incomplete_json,
    format_search_results_for_prompt
)


import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from utils.forum_reader import get_latest_host_speech, format_host_speech_for_prompt
    FORUM_READER_AVAILABLE = True
except ImportError:
    FORUM_READER_AVAILABLE = False
    logger.warning("Unable to import forum_reader module，HOST speech reading function will be skipped")


class FirstSummaryNode(StateMutationNode):
    """Generate the node for the first summary of the paragraph based on the search results."""
    
    def __init__(self, llm_client):
        """
        Initialize the first summary node
        
        Args:
            llm_client: LLM client
        """
        super().__init__(llm_client, "FirstSummaryNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "search_query", "search_results"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "search_query", "search_results"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> str:
        """
        Call LLM to generate paragraph summary
        
        Args:
            input_data: containstitle、content、search_queryand search_results data
            **kwargs: extra parameters
            
        Returns:
            Paragraph summary content
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("Input data format error")
            

            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data.copy() if isinstance(input_data, dict) else input_data
            

            if FORUM_READER_AVAILABLE:
                try:
                    host_speech = get_latest_host_speech()
                    if host_speech:

                        data['host_speech'] = host_speech
                        logger.info(f"HOST statement has been read，length: {len(host_speech)}character")
                except Exception as e:
                    logger.exception(f"Failed to read HOST statement: {str(e)}")
            

            message = json.dumps(data, ensure_ascii=False)
            

            if FORUM_READER_AVAILABLE and 'host_speech' in data and data['host_speech']:
                formatted_host = format_host_speech_for_prompt(data['host_speech'])
                message = formatted_host + "\n" + message
            
            logger.info("Generating first paragraph summary")
            

            response = self.llm_client.stream_invoke_to_string(
                SYSTEM_PROMPT_FIRST_SUMMARY,
                message,
            )
            

            processed_response = self.process_output(response)
            
            logger.info("Successfully generated the first paragraph summary")
            return processed_response
            
        except Exception as e:
            logger.exception(f"Failed to generate first summary: {str(e)}")
            raise e
    
    def process_output(self, output: str) -> str:
        """
        Processing LLM output，Extract paragraph content
        
        Args:
            output: LLM raw output
            
        Returns:
            Paragraph content
        """
        try:

            cleaned_output = remove_reasoning_from_output(output)
            cleaned_output = clean_json_tags(cleaned_output)
            

            logger.info(f"Cleaned output: {cleaned_output}")
            

            try:
                result = json.loads(cleaned_output)
                logger.info("JSONParsed successfully")
            except JSONDecodeError as e:
                logger.error(f"JSONParsing failed: {str(e)}")

                fixed_json = fix_incomplete_json(cleaned_output)
                if fixed_json:
                    try:
                        result = json.loads(fixed_json)
                        logger.info("JSONRepair successful")
                    except JSONDecodeError:
                        logger.exception("JSONRepair failed，Use the cleaned text directly")

                        return cleaned_output
                else:
                    logger.exception("cannot be repairedJSON，Use the cleaned text directly")

                    return cleaned_output
            

            if isinstance(result, dict):
                paragraph_content = result.get("paragraph_latest_state", "")
                if paragraph_content:
                    return paragraph_content
            

            return cleaned_output
            
        except Exception as e:
            logger.exception(f"Failed to process output: {str(e)}")
            return "Paragraph summary generation failed"
    
    def mutate_state(self, input_data: Any, state: State, paragraph_index: int, **kwargs) -> State:
        """
        Update the latest summary of the paragraph to the status
        
        Args:
            input_data: input data
            state: current state
            paragraph_index: paragraph index
            **kwargs: extra parameters
            
        Returns:
            Updated status
        """
        try:

            summary = self.run(input_data, **kwargs)
            

            if 0 <= paragraph_index < len(state.paragraphs):
                state.paragraphs[paragraph_index].research.latest_summary = summary
                logger.info(f"Paragraph updated {paragraph_index} first summary of")
            else:
                raise ValueError(f"paragraph index {paragraph_index} out of range")
            
            state.update_timestamp()
            return state
            
        except Exception as e:
            logger.exception(f"Status update failed: {str(e)}")
            raise e


class ReflectionSummaryNode(StateMutationNode):
    """Update paragraph summary nodes based on reflection search results"""
    
    def __init__(self, llm_client):
        """
        Initialize reflection summary node
        
        Args:
            llm_client: LLM client
        """
        super().__init__(llm_client, "ReflectionSummaryNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "search_query", "search_results", "paragraph_latest_state"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "search_query", "search_results", "paragraph_latest_state"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> str:
        """
        Call LLM to update paragraph content
        
        Args:
            input_data: data containing complete reflection information
            **kwargs: System startup
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("Input data format error")
            

            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data.copy() if isinstance(input_data, dict) else input_data
            

            if FORUM_READER_AVAILABLE:
                try:
                    host_speech = get_latest_host_speech()
                    if host_speech:

                        data['host_speech'] = host_speech
                        logger.info(f"HOST statement has been read，length: {len(host_speech)}character")
                except Exception as e:
                    logger.exception(f"Failed to read HOST statement: {str(e)}")
            

            message = json.dumps(data, ensure_ascii=False)
            

            if FORUM_READER_AVAILABLE and 'host_speech' in data and data['host_speech']:
                formatted_host = format_host_speech_for_prompt(data['host_speech'])
                message = formatted_host + "\n" + message
            
            logger.info("Generating reflection summary")
            

            response = self.llm_client.stream_invoke_to_string(
                SYSTEM_PROMPT_REFLECTION_SUMMARY,
                message,
            )
            

            processed_response = self.process_output(response)
            
            logger.info("Successfully generated reflection summary")
            return processed_response
            
        except Exception as e:
            logger.exception(f"Generating reflection summary failed: {str(e)}")
            raise e
    
    def process_output(self, output: str) -> str:
        """
        Processing LLM output，Extract updated paragraph content
        
        Args:
            output: LLM raw output
            
        Returns:
            Updated paragraph content
        """
        try:

            cleaned_output = remove_reasoning_from_output(output)
            cleaned_output = clean_json_tags(cleaned_output)
            

            logger.info(f"Cleaned output: {cleaned_output}")
            

            try:
                result = json.loads(cleaned_output)
                logger.info("JSONParsed successfully")
            except JSONDecodeError as e:
                logger.error(f"JSONParsing failed: {str(e)}")

                fixed_json = fix_incomplete_json(cleaned_output)
                if fixed_json:
                    try:
                        result = json.loads(fixed_json)
                        logger.info("JSONRepair successful")
                    except JSONDecodeError:
                        logger.error("JSONRepair failed，Use the cleaned text directly")

                        return cleaned_output
                else:
                    logger.error("cannot be repairedJSON，Use the cleaned text directly")

                    return cleaned_output
            

            if isinstance(result, dict):
                updated_content = result.get("updated_paragraph_latest_state", "")
                if updated_content:
                    return updated_content
            

            return cleaned_output
            
        except Exception as e:
            logger.exception(f"Failed to process output: {str(e)}")
            return "Reflection summary generation failed"
    
    def mutate_state(self, input_data: Any, state: State, paragraph_index: int, **kwargs) -> State:
        """
        Write updated summary to status
        
        Args:
            input_data: input data
            state: current state
            paragraph_index: paragraph index
            **kwargs: extra parameters
            
        Returns:
            Updated status
        """
        try:

            updated_summary = self.run(input_data, **kwargs)
            

            if 0 <= paragraph_index < len(state.paragraphs):
                state.paragraphs[paragraph_index].research.latest_summary = updated_summary
                state.paragraphs[paragraph_index].research.increment_reflection()
                logger.info(f"Paragraph updated {paragraph_index} Summary of reflections")
            else:
                raise ValueError(f"paragraph index {paragraph_index} out of range")
            
            state.update_timestamp()
            return state
            
        except Exception as e:
            logger.exception(f"Status update failed: {str(e)}")
            raise e
