"""
Relevance Scoring Module (LLM Enhanced)

Uses OpenAI's GPT-5.4 to intelligently determine if an article is a true FMCG deal,
filtering out false positives (like general market outlooks) and extracting core METADATA
(Buyer, Target, Value, Type).
"""
import json
import logging
import os
from typing import Dict, List, Tuple
from dotenv import load_dotenv
from openai import OpenAI

from pipeline.models import RawDeal

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def score_relevance(
    deals: List[RawDeal],
    config: dict,
) -> Tuple[List[Dict], int]:
    """
    Score relevance and extract entities using an LLM.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not found in environment or .env file.")
        raise ValueError("Missing OpenAI API Key in .env file.")

    client = OpenAI(api_key=api_key)
    
    llm_config = config.get("llm", {})
    # Fallback to gpt-4o-mini if gpt-5.4 is rejected by the user's specific key
    model = llm_config.get("model", "gpt-5.4")
    system_prompt = llm_config.get("system_prompt", "You are an FMCG analyst. Return JSON.")
    min_score = config.get("relevance", {}).get("min_score", 50)

    scored = []
    filtered_count = 0

    logger.info(f"Starting LLM relevance scoring for {len(deals)} articles using {model}...")

    for deal in deals:
        user_prompt = f"Title: {deal.title}\nSummary: {deal.summary}"
        
        try:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1
            )
            
            result_str = response.choices[0].message.content
            result = json.loads(result_str)
            
            is_deal = result.get("is_fmcg_deal", False)
            score = result.get("confidence_score", 0)
            
            if is_deal and score >= min_score:
                scored_record = deal.to_dict()
                scored_record["relevance_score"] = score
                scored_record["buyer"] = result.get("buyer") or ""
                scored_record["target"] = result.get("target") or ""
                scored_record["deal_value"] = result.get("deal_value") or ""
                scored_record["deal_type"] = result.get("deal_type") or "Unknown"
                
                scored.append(scored_record)
                logger.debug(f"  ✓ Valid Deal ({score}): {deal.title[:50]} (Buyer: {scored_record.get('buyer', '')})")
            else:
                filtered_count += 1
                logger.debug(f"  ✗ Filtered: {deal.title[:50]}")
                
        except Exception as e:
            logger.warning(f"LLM Error on deal '{deal.title[:30]}': {e}")
            filtered_count += 1 # Filter out on failure to be safe

    logger.info(
        f"LLM Relevance scoring: {len(deals)} articles → "
        f"{len(scored)} relevant, {filtered_count} filtered out"
    )

    # Sort by relevance score descending
    scored.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    return scored, filtered_count
