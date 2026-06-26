"""Kafka EventBus adapter for AeroCommand distributed deployment.

DOWN and UP CDM messages map to Kafka topics; drain() pulls from the topic.
Requires Kafka running (usually via docker-compose).
"""

import json
from typing import Any, List, Optional

from kafka import KafkaConsumer, KafkaProducer

from core.ports import EventBus


class KafkaEventBus(EventBus):
    """Kafka topic-backed event bus for distributed messaging."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        down_topic: str = "atc-flow-directives",
        up_topic: str = "aoc-responses",
        group_id: str = "aerocommand",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.down_topic = down_topic
        self.up_topic = up_topic
        self.group_id = group_id

        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        self.consumer = KafkaConsumer(
            down_topic,
            up_topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
        )

    def publish(self, message: Any) -> None:
        """Publish message to appropriate topic based on direction."""
        topic = self._topic_for(message)
        # Serialize to dict if it's a Pydantic model
        data = message.model_dump() if hasattr(message, "model_dump") else message
        self.producer.send(topic, value=data)

    def publish_many(self, messages: List[Any]) -> None:
        for msg in messages:
            self.publish(msg)

    def drain(self, **filters) -> List[Any]:
        """Pull messages from topics matching filters.

        For CDM: filters={'direction': CDMDirection.UP} or direction=CDMDirection.DOWN
        """
        messages = []
        timeout_ms = 1000
        for record in self.consumer.poll(timeout_ms=timeout_ms).values():
            for msg_record in record:
                data = msg_record.value
                if all(data.get(k) == v for k, v in filters.items()):
                    messages.append(data)
        return messages

    @property
    def pending(self) -> int:
        """Rough estimate of messages waiting (Kafka doesn't expose this easily)."""
        # A full implementation would track position vs. end offset
        return 0  # ponytail: placeholder until needed

    @staticmethod
    def _topic_for(message: Any) -> str:
        """Route message to appropriate topic based on direction attribute."""
        # Assume message has a 'direction' attribute (CDM protocol)
        direction = getattr(message, "direction", None)
        if direction and str(direction).endswith("DOWN"):
            return "atc-flow-directives"
        return "aoc-responses"

    def close(self):
        """Clean up Kafka connections."""
        self.producer.close()
        self.consumer.close()
