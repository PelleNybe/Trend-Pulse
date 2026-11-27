"""
Financial Committee Moderator LLM (formerly Forum Moderator).
Hosts debates between Quantitative, Fundamental, and Macro analysts.
Now with Agentic Memory (Mem0) integration for longitudinal discussion context.
"""

from loguru import logger
import json
from json_repair import repair_json

try:
    from mem0 import Memory
    mem0_available = True
    # Initialize Mem0 with local SQLite to avoid external dependencies by default
    config = {
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "forum_host_memory",
                "path": "./mem0_data"
            }
        }
    }
    host_memory = Memory.from_config(config)
    logger.info("Mem0 Host Memory initialized successfully.")
except Exception as e:
    mem0_available = False
    host_memory = None
    logger.warning(f"Mem0 not found or failed to initialize: {e}. Continuing without long-term agentic memory.")

class FinancialCommitteeHost:
    """
    Moderates the 'Financial Committee' debate, pushing agents to explore deeper
    market nuances rather than superficial sentiment.
    """
    def __init__(self, llm_client=None):
        self.llm = llm_client
        logger.info("Financial Committee Host initialized.")
        
    def synthesize_discussion(self, context, topic="General Market Discussion"):
        """
        Takes the current context of agent research and outputs guidance
        for the next round of analysis.
        """
        mem0_context = ""
        if mem0_available and host_memory:
            try:
                # Retrieve past relevant context for the LLM
                relevant_memories = host_memory.search(context, user_id="forum_agents", limit=3)
                if isinstance(relevant_memories, dict):
                    mem_items = relevant_memories.get("results", [])
                elif isinstance(relevant_memories, list):
                    mem_items = relevant_memories
                else:
                    mem_items = []
                mem_texts = [
                    m.get("memory", "")
                    for m in mem_items
                    if isinstance(m, dict) and m.get("memory")
                ]
                if mem_texts:
                    mem0_context = "PAST RELEVANT DISCUSSIONS TO INFORM YOUR DECISION:\n" + "\n".join(mem_texts) + "\n\n"
            except Exception as e:
                logger.error(f"Mem0 search failed: {e}")

        prompt = f"""
        You are the Chief Investment Officer (CIO) leading a committee of specialized analysts.
        Topic: {topic}
        Current Research Context: {context}
        
        {mem0_context}

        Task: Synthesize the current findings and provide strict directives for the
        Quantitative Analyst, Fundamental Analyst, and Macroeconomic Researcher.
        Avoid repetitive tasks. Push them to find alpha, uncover hidden risks,
        and provide actionable investment intelligence.
        
        Output valid JSON:
        {{
            "synthesis": "Summary of current findings",
            "directives": [
                {{"agent": "Fundamental Analyst", "directive": "Comprehensive dive into Q3 margins..."}},
                {{"agent": "Quantitative Analyst", "directive": "Analyze volatility skew and options volume..."}},
                {{"agent": "Macro Researcher", "directive": "Assess the impact of recent rate cuts..."}}
            ]
        }}
        """

        logger.info(f"Synthesizing financial discussion for topic: {topic}")

        if self.llm:
            try:
                response_str = self.llm.stream_invoke_to_string(prompt, ' ')
                start_idx = response_str.find('{')
                end_idx = response_str.rfind('}')
                if start_idx != -1 and end_idx > start_idx:
                    candidate = response_str[start_idx:end_idx + 1]
                    try:
                        json.loads(candidate)
                        response = candidate
                    except json.JSONDecodeError:
                        response = repair_json(candidate)
                else:
                    response = repair_json(response_str)
            except Exception as e:
                logger.error(f"Host LLM call failed: {e}")
                raise RuntimeError(f"Host LLM synthesis failed: {e}") from e
        else:
            raise RuntimeError(
                "FinancialCommitteeHost requires a configured LLM client (set FORUM_HOST_API_KEY and FORUM_HOST_MODEL_NAME)."
            )

        
        if mem0_available and host_memory:
            try:
                # Store the synthesis as a memory
                host_memory.add(response, user_id="forum_agents", metadata={"topic": topic})
            except Exception as e:
                logger.error(f"Mem0 save failed: {e}")

        return response

def generate_host_speech(recent_speeches):
    """
    Adapter function for monitor.py to call the new FinancialCommitteeHost.
    Takes a list of recent speeches (strings) and returns a formatted host speech.
    """

    try:
        from InsightEngine.llms import LLMClient
        from config import settings
        api_key = getattr(settings, "FORUM_HOST_API_KEY", None)
        model_name = getattr(settings, "FORUM_HOST_MODEL_NAME", None)
        base_url = getattr(settings, "FORUM_HOST_BASE_URL", None)
        if not api_key or not model_name:
            logger.warning("FORUM_HOST_API_KEY or FORUM_HOST_MODEL_NAME not configured; skipping host synthesis")
            return None
        llm_client = LLMClient(
            api_key=api_key,
            model_name=model_name,
            base_url=base_url,
        )
    except Exception as e:
        logger.warning(f"Failed to initialize LLM for Forum Host: {e}")
        return None

    try:
        host = FinancialCommitteeHost(llm_client=llm_client)

        context = "\n".join(str(s) for s in recent_speeches)
        result = host.synthesize_discussion(context)
        parsed = json.loads(result) if isinstance(result, str) else result

        speech_parts = [parsed.get("synthesis", "") + "\n\nDirectives:\n"]
        for directive in parsed.get("directives", []):
            speech_parts.append(f"- {directive.get('agent', 'Analyst')}: {directive.get('directive', '')}\n")
        return "".join(speech_parts)
    except Exception as e:
        logger.error(f"Failed to generate host speech: {e}")
        return None

if __name__ == "__main__":
    output = generate_host_speech(["Market Impact of Fed Rate Hikes: Initial data shows a tech sell-off."])
    print(output or "Forum Host LLM not configured.")
