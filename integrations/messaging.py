#!/usr/bin/env python3
"""
Messaging utilities for sending notifications to AI agent services via Google Cloud Tasks.
"""

import os
import json
from uuid import UUID
from typing import Dict, Any
from google.cloud import tasks_v2


async def send_raw_entry_notification(user_id: UUID, raw_entry, metadata: Dict[str, Any]):
    """
    Enqueue a task to send notification about new raw entry to AI agent service.
    
    Args:
        user_id: The user's UUID
        raw_entry: The RawEntry object that was created
        metadata: Additional metadata about the entry
    """
    try:
        # Get Google Cloud Tasks configuration
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1")
        queue_name = "messages"
        agent_service_url = os.getenv("AI_AGENT_SERVICE_URL")
        agent_service_token = os.getenv("AI_AGENT_SERVICE_TOKEN")

        if not project_id:
            print("   GOOGLE_CLOUD_PROJECT not configured - skipping notification")
            return

        if not agent_service_url:
            print("   AI_AGENT_SERVICE_URL not configured - skipping notification")
            return

        # Prepare the message payload
        message_data = {
            "type": "new_raw_entry",
            "raw_entry_id": str(raw_entry.id),
            "user_id": str(user_id),
            "source": getattr(raw_entry, 'source', 'unknown'),
            "content": raw_entry.content,
            "metadata": metadata,
            "timestamp": raw_entry.created_at.isoformat() if hasattr(raw_entry, 'created_at') else None
        }
        
        # Prepare the task payload for the agent service
        task_payload = {
            "user_id": str(user_id),
            "channel": "raw_data_entries",
            "message": json.dumps(message_data),
            "sender": "notion_importer"
        }
        
        # Prepare headers for the eventual HTTP request
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "everlight-api/messaging"
        }
        
        if agent_service_token:
            headers["Authorization"] = f"Bearer {agent_service_token}"
        
        # Create Cloud Tasks client
        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(project_id, location, queue_name)
        
        # Create the task
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{agent_service_url}/message",
                "headers": headers,
                "body": json.dumps(task_payload).encode()
            }
        }
        
        # Enqueue the task
        response = client.create_task(request={"parent": parent, "task": task})
        print(f"   Successfully enqueued notification task: {response.name}")
        
    except Exception as e:
        print(f"   Error enqueuing notification task: {e}")
        # Don't raise - we don't want notification failures to break page processing
