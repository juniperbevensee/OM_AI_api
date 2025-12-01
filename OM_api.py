#!/usr/bin/env python3
"""
Open Measures API Search Script
Search for content across various platforms using the Open Measures Public API
with AI-powered natural language search using Claude
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List


class OpenMeasuresAPI:
    """Simple wrapper for the Open Measures Public API"""
    
    BASE_URL = "https://api.openmeasures.io/content"
    
    # Available platforms
    SITES = ["telegram", "gettr", "win", "gab", "parler", "scored", "truthsocial"]
    
    # Query types
    QUERY_TYPES = ["content", "boolean_content", "query_string"]
    
    def __init__(self, claude_api_key: Optional[str] = None):
        self.session = requests.Session()
        self.claude_api_key = claude_api_key
        self.claude_api_url = "https://api.anthropic.com/v1/messages"
    
    def search(
        self,
        term: str,
        site: str = "telegram",
        limit: int = 10,
        since: Optional[str] = None,
        until: Optional[str] = None,
        querytype: str = "content",
        sortdesc: bool = False
    ) -> Dict[str, Any]:
        """
        Search for content on Open Measures platforms
        
        Args:
            term: Search term or query
            site: Platform to search (telegram, gettr, win, gab, parler, scored, truthsocial)
            limit: Maximum number of results (max 10000)
            since: Start date (ISO format or None for default)
            until: End date (ISO format or None for default)
            querytype: Type of query - "content", "boolean_content", or "query_string"
            sortdesc: Sort results in descending order
            
        Returns:
            Dictionary containing API response with search results
        """
        
        # Build parameters
        params = {
            "term": term,
            "site": site,
            "limit": min(limit, 10000),  # Cap at API maximum
            "querytype": querytype,
            "sortdesc": str(sortdesc).lower()
        }
        
        # Add date parameters if provided
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        
        try:
            response = self.session.get(self.BASE_URL, params=params)
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            print(f"Error making request: {e}")
            return {"error": str(e)}
    
    def simple_search(self, term: str, site: str = "telegram", limit: int = 10) -> list:
        """
        Simplified search that returns just the list of results
        
        Args:
            term: Search term
            site: Platform to search
            limit: Maximum number of results
            
        Returns:
            List of result documents
        """
        response = self.search(term=term, site=site, limit=limit)
        
        if "error" in response:
            return []
        
        try:
            return response.get("hits", {}).get("hits", [])
        except (KeyError, AttributeError):
            return []
    
    def call_claude(self, prompt: str) -> str:
        """
        Call Claude API with a prompt
        
        Args:
            prompt: The prompt to send to Claude
            
        Returns:
            Claude's response text
        """
        if not self.claude_api_key:
            return "Error: Claude API key not set"
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.claude_api_key,
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            response = requests.post(self.claude_api_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            return result["content"][0]["text"]
        except requests.exceptions.RequestException as e:
            return f"Error calling Claude API: {e}"
    
    def natural_language_search(self, user_query: str) -> Dict[str, Any]:
        """
        Use Claude to interpret a natural language query and execute the search
        
        Args:
            user_query: Natural language search request
            
        Returns:
            Dictionary with search results and summary
        """
        if not self.claude_api_key:
            return {"error": "Claude API key not set"}
        
        # First, ask Claude to parse the query into API parameters
        parse_prompt = f"""Given this natural language search query, extract the search parameters for the Open Measures API.

User query: "{user_query}"

Available platforms: {', '.join(self.SITES)}
Query types: content (simple search), boolean_content (AND/OR logic), query_string (advanced field search)

Return a JSON object with these fields:
- term: the search term or query
- site: the platform to search (default: telegram)
- limit: number of results (default: 20, max: 10000)
- querytype: type of query (default: content)

Only return the JSON object, nothing else."""

        print("🤖 Claude is parsing your query...")
        parse_response = self.call_claude(parse_prompt)
        
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = parse_response.strip()
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1])
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()
            
            params = json.loads(json_str)
            
            print(f"\n📊 Search parameters:")
            print(f"  Term: {params.get('term')}")
            print(f"  Site: {params.get('site')}")
            print(f"  Limit: {params.get('limit')}")
            print(f"  Query type: {params.get('querytype')}")
            print("\n🔍 Searching Open Measures API...")
            
            # Execute the search
            results = self.search(
                term=params.get("term", ""),
                site=params.get("site", "telegram"),
                limit=params.get("limit", 20),
                querytype=params.get("querytype", "content")
            )
            
            if "error" in results:
                return {"error": results["error"]}
            
            hits = results.get("hits", {}).get("hits", [])
            
            if not hits:
                return {
                    "params": params,
                    "results": [],
                    "summary": "No results found for this query."
                }
            
            # Prepare results for summarization
            results_text = self._format_results_for_summary(hits[:20])  # Limit to 20 for summary
            
            # Ask Claude to summarize the results
            summary_prompt = f"""Analyze and summarize these search results from the Open Measures API.

Original query: "{user_query}"
Search term: "{params.get('term')}"
Platform: {params.get('site')}
Number of results: {len(hits)}

Results:
{results_text}

Provide a concise summary that includes:
1. Key themes and topics found
2. Notable patterns or trends
3. Any significant usernames or sources mentioned
4. Overall sentiment or tone if apparent

Keep the summary under 300 words."""

            print("🤖 Claude is analyzing the results...\n")
            summary = self.call_claude(summary_prompt)
            
            return {
                "params": params,
                "results": hits,
                "summary": summary,
                "total_found": len(hits)
            }
            
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse Claude's response: {e}\nResponse: {parse_response}"}
        except Exception as e:
            return {"error": f"Error during natural language search: {e}"}
    
    def _format_results_for_summary(self, hits: List[Dict]) -> str:
        """Format search results for Claude to summarize"""
        formatted = []
        for i, hit in enumerate(hits[:20], 1):
            source = hit.get("_source", {})
            text = (source.get("message") or source.get("txt") or source.get("content") or "")[:500]
            username = source.get("uinf", {}).get("username", "Unknown")
            timestamp = source.get("timestamp", "N/A")
            
            formatted.append(f"Result {i}:\nUser: {username}\nTime: {timestamp}\nText: {text}\n")
        
        return "\n".join(formatted)


def ai_search_mode():
    """AI-powered natural language search mode"""
    print("\n" + "=" * 60)
    print("AI-Powered Search Mode (Powered by Claude)")
    print("=" * 60)
    
    # Get Claude API key
    api_key = input("\nEnter your Claude API key: ").strip()
    
    if not api_key:
        print("Error: API key is required for AI search mode")
        return
    
    # Initialize API with Claude key
    api = OpenMeasuresAPI(claude_api_key=api_key)
    
    print("\n✨ AI search is ready! You can now ask in natural language.")
    print("Examples:")
    print('  - "Search for telegram posts about Trump from the last month"')
    print('  - "Find Gettr posts from user miles about crypto"')
    print('  - "Show me recent discussions about climate change on Gab"')
    print("\nType 'quit' to exit.\n")
    
    while True:
        user_query = input("Your search request: ").strip()
        
        if user_query.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if not user_query:
            continue
        
        print()
        result = api.natural_language_search(user_query)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            continue
        
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(result["summary"])
        print("\n" + "=" * 60)
        print(f"Found {result['total_found']} results")
        print("=" * 60)
        
        # Ask if user wants additional analysis
        while True:
            additional = input("\nWould you like AI to perform any other analysis on these results? (y/n): ").strip().lower()
            
            if additional == 'y':
                analysis_query = input("What would you like to analyze? (e.g., 'identify main actors', 'find conspiracy theories', 'sentiment breakdown'): ").strip()
                
                if analysis_query:
                    results_text = api._format_results_for_summary(result["results"][:20])
                    
                    custom_prompt = f"""Analyze these search results from the Open Measures API based on the user's request.

Original search: "{user_query}"
Platform: {result['params'].get('site')}
Number of results: {result['total_found']}

User's analysis request: "{analysis_query}"

Results:
{results_text}

Provide a detailed analysis addressing the user's specific request. Include specific examples and evidence from the results."""

                    print("\n🤖 Claude is analyzing...\n")
                    custom_analysis = api.call_claude(custom_prompt)
                    
                    print("=" * 60)
                    print("CUSTOM ANALYSIS")
                    print("=" * 60)
                    print(custom_analysis)
                    print("=" * 60)
            else:
                break
        
        # Ask if user wants to see raw results
        show_raw = input("\nShow raw results? (y/n): ").strip().lower()
        if show_raw == 'y':
            for i, hit in enumerate(result["results"][:10], 1):
                source = hit.get("_source", {})
                text = (source.get("message") or source.get("txt") or source.get("content") or "")
                username = source.get("uinf", {}).get("username", "N/A")
                timestamp = source.get("timestamp", "N/A")
                
                print(f"\nResult {i}:")
                print(f"  User: {username}")
                print(f"  Time: {timestamp}")
                print(f"  Text: {text[:300]}{'...' if len(text) > 300 else ''}")
                print("-" * 60)
        
        print("\n")


def main():
    """Interactive search using the Open Measures API"""
    
    print("=" * 60)
    print("Open Measures API Search Tool")
    print("=" * 60)
    print("\nChoose search mode:")
    print("  1. Manual search (specify parameters yourself)")
    print("  2. AI-powered search (natural language with Claude)")
    
    mode = input("\nEnter mode (1/2): ").strip()
    
    if mode == "2":
        ai_search_mode()
        return
    
    # Original manual search mode
    # Initialize API client
    api = OpenMeasuresAPI()
    
    print("=" * 60)
    print("Open Measures API Search Tool")
    print("=" * 60)
    
    # Get search term
    search_term = input("\nEnter search term: ").strip()
    
    if not search_term:
        print("Error: Search term cannot be empty")
        return
    
    # Get platform
    print(f"\nAvailable platforms: {', '.join(api.SITES)}")
    site = input("Enter platform (default: telegram): ").strip().lower() or "telegram"
    
    if site not in api.SITES:
        print(f"Warning: '{site}' may not be valid. Using anyway...")
    
    # Get query type
    print(f"\nQuery types:")
    print("  1. content - Simple search in content")
    print("  2. boolean_content - Boolean logic (AND, OR, NOT)")
    print("  3. query_string - Advanced field-specific search")
    query_choice = input("Enter query type (1/2/3, default: 1): ").strip() or "1"
    
    query_type_map = {
        "1": "content",
        "2": "boolean_content",
        "3": "query_string"
    }
    querytype = query_type_map.get(query_choice, "content")
    
    # Get limit
    limit_input = input("\nNumber of results (default: 10, max: 10000): ").strip()
    try:
        limit = int(limit_input) if limit_input else 10
    except ValueError:
        print("Invalid number, using default of 10")
        limit = 10
    
    # Perform search
    print("\n" + "=" * 60)
    print(f"Searching for: '{search_term}' on {site}")
    print(f"Query type: {querytype}")
    print("=" * 60 + "\n")
    
    results = api.search(
        term=search_term,
        site=site,
        limit=limit,
        querytype=querytype
    )
    
    # Display results
    if "error" in results:
        print(f"Error: {results['error']}")
        return
    
    hits = results.get("hits", {}).get("hits", [])
    total = results.get("hits", {}).get("total", {})
    
    if isinstance(total, dict):
        total_value = total.get("value", 0)
    else:
        total_value = total
    
    print(f"Found {len(hits)} results (total matching: {total_value})\n")
    
    if not hits:
        print("No results found.")
        return
    
    # Display each result
    for i, result in enumerate(hits, 1):
        source = result.get("_source", {})
        
        # Try different text fields depending on platform
        text = (source.get("message") or 
                source.get("txt") or 
                source.get("content") or 
                "")
        
        timestamp = source.get("timestamp", "N/A")
        username = source.get("uinf", {}).get("username", "N/A")
        
        print(f"Result {i}:")
        print(f"  User: {username}")
        print(f"  Time: {timestamp}")
        print(f"  Text: {text[:300]}{'...' if len(text) > 300 else ''}")
        print("-" * 60)


if __name__ == "__main__":
    main()