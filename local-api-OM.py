#!/usr/bin/env python3
"""
Open Measures API Server
REST API server for natural language searches to Open Measures
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
from typing import Optional, Dict, Any

# ============================================================================
# CONFIGURATION - Set your Claude API key here
# ============================================================================
CLAUDE_API_KEY = "your-claude-api-key-here"
# ============================================================================

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes


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
        """
        params = {
            "term": term,
            "site": site,
            "limit": min(limit, 10000),
            "querytype": querytype,
            "sortdesc": str(sortdesc).lower()
        }
        
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        
        try:
            response = self.session.get(self.BASE_URL, params=params)
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def call_claude(self, prompt: str) -> str:
        """Call Claude API with a prompt"""
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
    
    def parse_natural_language_query(self, user_query: str) -> Dict[str, Any]:
        """Use Claude to parse natural language into search parameters"""
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

        response = self.call_claude(parse_prompt)
        
        try:
            json_str = response.strip()
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1])
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()
            
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse query: {e}"}


# API Routes

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "Open Measures API Server"})


@app.route('/search', methods=['POST'])
def search():
    """
    Natural language search endpoint
    
    Takes human-readable text, parses it with Claude, executes the search,
    and returns the raw Open Measures API response.
    
    Supports both formats:
    1. Simple: {"query": "Search telegram for Trump"}
    2. OpenAI chat format: Extracts content from last message in messages array
    
    Response:
    Returns either raw Open Measures data or OpenAI-formatted chat completion
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Missing request body"}), 400
    
    # Detect if this is an OpenAI chat completion request
    is_chat_completion = 'messages' in data and 'model' in data
    
    # Extract query from either format
    query = None
    
    # Format 1: Simple query format
    if 'query' in data:
        query = data['query']
    
    # Format 2: OpenAI chat completion format
    elif 'messages' in data and isinstance(data['messages'], list) and len(data['messages']) > 0:
        # Get the last message
        last_message = data['messages'][-1]
        if isinstance(last_message, dict) and 'content' in last_message:
            query = last_message['content']
            
            # If the content has the [actor] format, extract just the message part
            # Format: "[actor-name (actor-id) at timestamp]:\nActual message"
            if isinstance(query, str) and ']:' in query:
                # Split on the first occurrence of ']:\n' or ']:'
                parts = query.split(']:', 1)
                if len(parts) > 1:
                    query = parts[1].strip()
    
    if not query:
        return jsonify({"error": "Missing query. Provide either 'query' field or 'messages' array"}), 400
    
    if not CLAUDE_API_KEY or CLAUDE_API_KEY == "your-claude-api-key-here":
        return jsonify({"error": "Claude API key not configured. Please set CLAUDE_API_KEY in the code."}), 500
    
    api = OpenMeasuresAPI(claude_api_key=CLAUDE_API_KEY)
    
    # Parse natural language query
    params = api.parse_natural_language_query(query)
    
    if 'error' in params:
        if is_chat_completion:
            return jsonify({
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": f"Error parsing query: {params['error']}"
                    },
                    "finish_reason": "stop"
                }]
            })
        return jsonify({"error": params['error'], "stage": "parsing"}), 400
    
    # Execute search with parsed parameters
    results = api.search(
        term=params.get('term', ''),
        site=params.get('site', 'telegram'),
        limit=params.get('limit', 20),
        querytype=params.get('querytype', 'content')
    )
    
    # If this is a chat completion request, format the response accordingly
    if is_chat_completion:
        # Format the Open Measures results as a readable message
        hits = results.get('hits', {}).get('hits', [])
        total_hits = results.get('hits', {}).get('total', {})
        if isinstance(total_hits, dict):
            total_hits = total_hits.get('value', 0)
        
        # Build the actual API request URL (always show this)
        api_request_url = f"{api.BASE_URL}?term={params.get('term')}&site={params.get('site')}&limit={params.get('limit')}&querytype={params.get('querytype')}"
        
        if 'error' in results:
            response_content = f"Error searching Open Measures: {results['error']}\n\n"
            response_content += f"**API Request Sent:**\n```\n{api_request_url}\n```"
        elif not hits:
            response_content = f"❌ No results found for: {query}\n\n"
            response_content += f"**Search Parameters:**\n"
            response_content += f"- Term: `{params.get('term')}`\n"
            response_content += f"- Platform: `{params.get('site')}`\n"
            response_content += f"- Query Type: `{params.get('querytype')}`\n"
            response_content += f"- Limit: `{params.get('limit')}`\n\n"
            response_content += f"**API Request Sent:**\n```\n{api_request_url}\n```"
        else:
            # Format results as a readable message
            response_content = f"✅ Open Measures Search Complete\n\n"
            response_content += f"**Search Parameters:**\n"
            response_content += f"- Term: `{params.get('term')}`\n"
            response_content += f"- Platform: `{params.get('site')}`\n"
            response_content += f"- Query Type: `{params.get('querytype')}`\n"
            response_content += f"- Limit: `{params.get('limit')}`\n"
            response_content += f"- Results Received: `{len(hits)}`\n"
            response_content += f"- Total Available: `{total_hits}`\n\n"
            response_content += f"**API Request Sent:**\n```\n{api_request_url}\n```\n\n"
            response_content += "**Raw JSON Results:**\n```json\n"
            response_content += json.dumps(results, indent=2)
            response_content += "\n```"
        
        return jsonify({
            "id": "chatcmpl-openmeasures",
            "object": "chat.completion",
            "created": int(request.headers.get('X-Request-Time', '0')) or 1234567890,
            "model": data.get('model', 'openai/gpt-oss-20b'),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_content
                },
                "finish_reason": "stop"
            }]
        })
    
    # Return the raw Open Measures API response for simple queries
    return jsonify(results)


@app.route('/sites', methods=['GET'])
def get_sites():
    """Get list of available platforms"""
    return jsonify({
        "sites": OpenMeasuresAPI.SITES,
        "query_types": OpenMeasuresAPI.QUERY_TYPES
    })


if __name__ == '__main__':
    print("=" * 60)
    print("Open Measures API Server")
    print("=" * 60)
    print("\nEndpoints:")
    print("  GET  /health    - Health check")
    print("  POST /search    - Natural language search")
    print("  GET  /sites     - List available platforms")
    print("\nStarting server on http://localhost:5000")
    print("=" * 60)
    print("\nExample requests:")
    print("\n1. Simple format:")
    print('  curl -X POST http://localhost:5000/search \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"query": "Search telegram for Trump"}\'')
    print("\n2. OpenAI chat format (extracts last message):")
    print('  curl -X POST http://localhost:5000/search \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"messages": [{"role": "user", "content": "Search telegram for Trump"}]}\'')
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)