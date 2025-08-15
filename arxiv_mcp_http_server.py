#!/usr/bin/env python3
"""
HTTP-based arXiv MCP server compatible with Microsoft Copilot Studio
Uses FastAPI to implement the streamable HTTP transport protocol
"""

import arxiv
import json
import os
from typing import List, Optional
from enum import Enum
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
from datetime import datetime, timedelta

# Enhanced for Google Colab compatibility
PAPER_DIR = "/content/papers" if os.path.exists("/content") else "papers"

# Get port from environment variable (Render sets this, defaults to 8001 for local dev)
PORT = int(os.environ.get("PORT", 8001))

# Create FastAPI app
app = FastAPI(
    title="Enhanced arXiv MCP Server",
    description="MCP server for searching and managing arXiv papers",
    version="1.0.0"
)

class SearchField(Enum):
    """Available search fields for arXiv queries"""
    ALL = "all"
    TITLE = "ti"
    AUTHOR = "au"
    ABSTRACT = "abs"
    COMMENT = "co"
    JOURNAL_REF = "jr"
    CATEGORY = "cat"
    REPORT_NUMBER = "rn"

class SortOption(Enum):
    """Available sort options for arXiv queries"""
    RELEVANCE = "relevance"
    SUBMITTED_DATE = "submittedDate"
    LAST_UPDATED_DATE = "lastUpdatedDate"

# MCP Tools Implementation
def search_papers(
    query: str, 
    max_results: int = 5,
    sort_by: str = "relevance",
    sort_order: str = "descending",
    search_field: str = "all",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    author_search: Optional[str] = None
) -> dict:
    """
    Enhanced search for papers on arXiv with advanced filtering options.
    """
    
    # Validate and convert sort_by
    sort_mapping = {
        "relevance": arxiv.SortCriterion.Relevance,
        "submitted": arxiv.SortCriterion.SubmittedDate,
        "submitteddate": arxiv.SortCriterion.SubmittedDate,
        "updated": arxiv.SortCriterion.LastUpdatedDate,
        "lastupdated": arxiv.SortCriterion.LastUpdatedDate,
        "lastupdateddate": arxiv.SortCriterion.LastUpdatedDate
    }
    sort_criterion = sort_mapping.get(sort_by.lower().replace("_", ""), arxiv.SortCriterion.Relevance)
    
    # Validate and convert sort_order
    order_mapping = {
        "desc": arxiv.SortOrder.Descending,
        "descending": arxiv.SortOrder.Descending,
        "asc": arxiv.SortOrder.Ascending,
        "ascending": arxiv.SortOrder.Ascending
    }
    sort_order_enum = order_mapping.get(sort_order.lower(), arxiv.SortOrder.Descending)
    
    # Build the search query with field prefixes
    search_query_parts = []
    
    # Handle field-specific search
    field_mapping = {
        "title": "ti",
        "author": "au", 
        "abstract": "abs",
        "category": "cat",
        "comment": "co",
        "journal": "jr",
        "all": "all"
    }
    field_prefix = field_mapping.get(search_field.lower(), "all")
    
    # Proper query construction for arXiv API
    if field_prefix != "all":
        search_query_parts.append(f"{field_prefix}:{query}")
    else:
        search_query_parts.append(query)
    
    # Add author search if specified
    if author_search:
        clean_author = author_search.replace(" ", "_").lower()
        search_query_parts.append(f"au:{clean_author}")
    
    # Add date filtering if specified
    if date_from or date_to:
        if date_from and date_to:
            search_query_parts.append(f"submittedDate:[{date_from}0000 TO {date_to}2359]")
        elif date_from:
            search_query_parts.append(f"submittedDate:[{date_from}0000 TO *]")
        elif date_to:
            search_query_parts.append(f"submittedDate:[* TO {date_to}2359]")
    
    # Combine all parts with AND
    final_query = " AND ".join(search_query_parts)
    
    # Use arxiv to find the papers 
    client = arxiv.Client()
    
    # Create search with enhanced parameters
    search = arxiv.Search(
        query=final_query,
        max_results=max_results,
        sort_by=sort_criterion,
        sort_order=sort_order_enum
    )

    papers = client.results(search)

    # Create directory structure
    query_slug = query.lower().replace(" ", "_").replace("/", "_")[:50]
    if author_search:
        query_slug += f"_by_{author_search.replace(' ', '_')}"
    
    path = os.path.join(PAPER_DIR, query_slug)
    os.makedirs(path, exist_ok=True)

    file_path = os.path.join(path, "papers_info.json")

    # Try to load existing papers info
    try:
        with open(file_path, "r", encoding='utf-8') as json_file:
            papers_info = json.load(json_file)
    except (FileNotFoundError, json.JSONDecodeError):
        papers_info = {}

    # Process each paper and add to papers_info  
    paper_ids = []
    new_papers_count = 0
    
    for paper in papers:
        paper_id = paper.get_short_id()
        paper_ids.append(paper_id)
        
        if paper_id not in papers_info:  # Only process if new
            new_papers_count += 1
            paper_info = {
                'title': paper.title,
                'authors': [author.name for author in paper.authors],
                'summary': paper.summary,
                'pdf_url': paper.pdf_url,
                'published': str(paper.published.date()),
                'updated': str(paper.updated.date()) if paper.updated else str(paper.published.date()),
                'categories': paper.categories,
                'primary_category': paper.primary_category,
                'entry_id': paper.entry_id,
                'search_params': {
                    'query': query,
                    'sort_by': sort_by,
                    'search_field': search_field,
                    'author_search': author_search,
                    'date_range': f"{date_from} to {date_to}" if date_from or date_to else None
                }
            }
            papers_info[paper_id] = paper_info

    # Save updated papers_info to json file
    with open(file_path, "w", encoding='utf-8') as json_file:
        json.dump(papers_info, json_file, indent=2, ensure_ascii=False)

    # Return comprehensive results
    return {
        "paper_ids": paper_ids,
        "total_found": len(paper_ids),
        "new_papers": new_papers_count,
        "search_query": final_query,
        "search_parameters": {
            "original_query": query,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "search_field": search_field,
            "author_search": author_search,
            "date_from": date_from,
            "date_to": date_to,
            "max_results": max_results
        },
        "storage_path": file_path,
        "message": f"Found {len(paper_ids)} papers ({new_papers_count} new). Results saved to {file_path}"
    }

def search_by_author(author_name: str, max_results: int = 10, sort_by: str = "submittedDate") -> dict:
    """Simplified tool specifically for author searches."""
    return search_papers(
        query="*",  # Match all papers
        max_results=max_results,
        sort_by=sort_by,
        search_field="author",
        author_search=author_name
    )

def search_recent_papers(topic: str, days_back: int = 7, max_results: int = 10) -> dict:
    """Search for recent papers on a topic within the last N days."""
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    date_from = start_date.strftime("%Y%m%d")
    date_to = end_date.strftime("%Y%m%d")
    
    return search_papers(
        query=topic,
        max_results=max_results,
        sort_by="submittedDate",
        sort_order="descending",
        date_from=date_from,
        date_to=date_to
    )

def extract_info(paper_id: str) -> str:
    """Search for information about a specific paper across all topic directories."""
    if not os.path.exists(PAPER_DIR):
        return f"Papers directory {PAPER_DIR} does not exist. No saved papers found."

    for item in os.listdir(PAPER_DIR):
        item_path = os.path.join(PAPER_DIR, item)
        if os.path.isdir(item_path):
            file_path = os.path.join(item_path, "papers_info.json")
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "r", encoding='utf-8') as json_file:
                        papers_info = json.load(json_file)
                        if paper_id in papers_info:
                            return json.dumps(papers_info[paper_id], indent=2, ensure_ascii=False)
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    print(f"Error reading {file_path}: {str(e)}")
                    continue

    return f"No saved information found for paper {paper_id}."

# MCP Tool definitions
MCP_TOOLS = [
    {
        "name": "search_papers",
        "description": "Enhanced search for papers on arXiv with advanced filtering options",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The main search term/topic"},
                "max_results": {"type": "integer", "default": 5, "description": "Maximum number of results to retrieve"},
                "sort_by": {"type": "string", "default": "relevance", "description": "Sort criterion"},
                "sort_order": {"type": "string", "default": "descending", "description": "Sort order"},
                "search_field": {"type": "string", "default": "all", "description": "Field to search in"},
                "date_from": {"type": "string", "description": "Start date for filtering (YYYYMMDD format)"},
                "date_to": {"type": "string", "description": "End date for filtering (YYYYMMDD format)"},
                "author_search": {"type": "string", "description": "Specific author to search for"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_by_author",
        "description": "Simplified tool specifically for author searches",
        "inputSchema": {
            "type": "object",
            "properties": {
                "author_name": {"type": "string", "description": "Full name of the author to search for"},
                "max_results": {"type": "integer", "default": 10, "description": "Maximum number of results"},
                "sort_by": {"type": "string", "default": "submittedDate", "description": "Sort criterion"}
            },
            "required": ["author_name"]
        }
    },
    {
        "name": "search_recent_papers",
        "description": "Search for recent papers on a topic within the last N days",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The research topic to search for"},
                "days_back": {"type": "integer", "default": 7, "description": "Number of days to look back"},
                "max_results": {"type": "integer", "default": 10, "description": "Maximum number of results"}
            },
            "required": ["topic"]
        }
    },
    {
        "name": "extract_info",
        "description": "Search for information about a specific paper across all topic directories",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "The ID of the paper to look for"}
            },
            "required": ["paper_id"]
        }
    }
]

# HTTP Endpoints

@app.get("/mcp")
async def health_check():
    """
    Health check endpoint required for Microsoft Copilot Studio compatibility.
    Power Platform automatically adds GET operations for MCP endpoints.
    """
    return {
        "status": "ok",
        "protocol": "mcp-streamable-1.0",
        "message": "Enhanced arXiv MCP server is running",
        "server": "enhanced_research",
        "version": "1.0.0"
    }

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """
    Main MCP endpoint for handling JSON-RPC requests
    Supports tools/list and tools/call methods
    """
    try:
        body = await request.json()
        
        # Validate JSON-RPC format
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
            raise HTTPException(status_code=400, detail="Invalid JSON-RPC request")
        
        method = body.get("method")
        request_id = body.get("id")
        params = body.get("params", {})
        
        if method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": MCP_TOOLS
                }
            }
            return JSONResponse(content=response)
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            # Execute the requested tool
            if tool_name == "search_papers":
                result = search_papers(**arguments)
            elif tool_name == "search_by_author":
                result = search_by_author(**arguments)
            elif tool_name == "search_recent_papers":
                result = search_recent_papers(**arguments)
            elif tool_name == "extract_info":
                result = extract_info(**arguments)
            else:
                raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
            
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, ensure_ascii=False)
                        }
                    ]
                }
            }
            return JSONResponse(content=response)
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown method: {method}")
    
    except Exception as e:
        error_response = {
            "jsonrpc": "2.0",
            "id": body.get("id") if 'body' in locals() else None,
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": str(e)
            }
        }
        return JSONResponse(content=error_response, status_code=500)

if __name__ == "__main__":
    # Ensure papers directory exists
    os.makedirs(PAPER_DIR, exist_ok=True)
    
    print(f"Starting Enhanced arXiv MCP HTTP server on 0.0.0.0:{PORT}")
    print(f"Papers will be stored in: {PAPER_DIR}")
    print(f"Health check endpoint: http://localhost:{PORT}/mcp")
    print(f"MCP endpoint: POST http://localhost:{PORT}/mcp")
    
    # Check if running in Google Colab
    if "/content" in PAPER_DIR:
        print("🔬 Google Colab environment detected - papers will persist in /content/papers")
    
    # Run with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)