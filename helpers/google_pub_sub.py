import inspect
import json
from datetime import datetime

from google.oauth2 import service_account
from google.api_core import retry
from google.cloud import pubsub_v1

from config import settings

GCP_CREDENTIALS = service_account.Credentials.from_service_account_file(
    filename=settings.gcs.gcp_service_account_filepath)


async def subscribe(project_id: str, subscription_id: str, callback):
    subscriber = pubsub_v1.SubscriberClient(credentials=GCP_CREDENTIALS)
    subscription_path = subscriber.subscription_path(project_id, subscription_id)

    NUM_MESSAGES = 1
    # Wrap the subscriber in a 'with' block to automatically call close() to
    # close the underlying gRPC channel when done.
    with subscriber:
        # The subscriber pulls a specific number of messages. The actual
        # number of messages pulled may be smaller than max_messages.
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": NUM_MESSAGES},
            retry=retry.Retry(deadline=300),
        )

        if len(response.received_messages) == 0:
            return

        ack_ids = []
        for received_message in response.received_messages:
            ack_ids.append(received_message.ack_id)

        # Acknowledges the received messages so they will not be sent again.
        subscriber.acknowledge(
            request={"subscription": subscription_path, "ack_ids": ack_ids}
        )

        for received_message in response.received_messages:
            try:
                # Check if the callback function is asynchronous
                if inspect.iscoroutinefunction(callback):
                    await callback(received_message.message.data.decode("utf-8"))
                else:
                    callback(received_message.message.data.decode("utf-8"))
            except Exception as e:
                print(e)


def publish(project_id: str, topic_id: str, content: str, log_level: str = "INFO") -> None:
    """
    Function to publish formatted logs to Google Cloud Pub/Sub
    """
    # Add timestamp and log level to the content
    event_dict = {"log_level": log_level, "content": content}

    # Convert event_dict to JSON string
    json_data = json.dumps(event_dict)

    # Encode the JSON string to bytes
    encoded_data = json_data.encode('utf-8')
    publisher = pubsub_v1.PublisherClient(credentials=GCP_CREDENTIALS)
    topic_path = publisher.topic_path(project_id, topic_id)

    try:
        future = publisher.publish(topic_path, data=encoded_data)
        result = future.result()
        print(f"Published log successfully. Message ID: {result}")
    except Exception as e:
        print(f"Failed to publish log: {str(e)}")