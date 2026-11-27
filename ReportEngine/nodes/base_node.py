"""
Report Enginenode base class。

All high-level inference nodes inherit from this，Unified log、Input verification and status change interface。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from ..llms.base import LLMClient
from ..state.state import ReportState
from loguru import logger

class BaseNode(ABC):
    """
    node base class。

    Unified implementation of logging tools、Input/output hooks and LLM client dependency injection，
    It is convenient for all nodes to focus only on business logic。
    """
    
    def __init__(self, llm_client: LLMClient, node_name: str = ""):
        """
        Initialize node
        
        Args:
            llm_client: LLM client
            node_name: node name

        BaseNode will save the node name to uniformly output log prefixes。
        """
        self.llm_client = llm_client
        self.node_name = node_name or self.__class__.__name__
    
    @abstractmethod
    def run(self, input_data: Any, **kwargs) -> Any:
        """
        Execute node processing logic
        
        Args:
            input_data: input data
            **kwargs: extra parameters
            
        Returns:
            Processing results
        """
        pass
    
    def validate_input(self, input_data: Any) -> bool:
        """
        Validate input data。
        Pass directly by default，Subclasses can override field checks as needed。
        
        Args:
            input_data: Enter data
            
        Returns:
            Verification passed
        """
        return True
    
    def process_output(self, output: Any) -> Any:
        """
        Process output data。
        Subclasses can override for structuring or validation。
        
        Args:
            output: raw output
            
        Returns:
            Processed output
        """
        return output
    
    def log_info(self, message: str):
        """Record information log，And automatically add the node name as a prefix。"""
        formatted_message = f"[{self.node_name}] {message}"
        logger.info(formatted_message)
    
    def log_error(self, message: str):
        """Record error log，Usually there are bold marks or typical header words。"""
        formatted_message = f"[{self.node_name}] {message}"
        logger.error(formatted_message)


class StateMutationNode(BaseNode):
    """
    Node base class with status modification function。

    Suitable for scenarios where nodes need to directly write to ReportState。
    """
    
    @abstractmethod
    def mutate_state(self, input_data: Any, state: ReportState, **kwargs) -> ReportState:
        """
        Modify status。

        The subclass needs to return a new status object or modify it in place and then return it.，For pipeline records。
        
        Args:
            input_data: Enter data
            state: current state
            **kwargs: extra parameters
            
        Returns:
            modified status
        """
        pass
