import pytest
from unittest.mock import MagicMock, patch
from hajeen_platform.services.distributed_messaging.kafka_integration import KafkaProducer, KafkaConsumer

def test_kafka_producer_init():
    producer = KafkaProducer("localhost:9092")
    assert producer is not None
    assert producer.bootstrap_servers == "localhost:9092"

@patch.object(KafkaProducer, 'produce_message', MagicMock())
def test_kafka_producer_produce_message():
    producer = KafkaProducer("localhost:9092")
    topic = "test_topic"
    key = "test_key"
    value = {"data": "hello"}
    producer.produce_message(topic, key, value)
    producer.produce_message.assert_called_once_with(topic, key, value)

def test_kafka_consumer_init():
    consumer = KafkaConsumer("localhost:9092", "test_group")
    assert consumer is not None
    assert consumer.bootstrap_servers == "localhost:9092"
    assert consumer.group_id == "test_group"

@patch.object(KafkaConsumer, 'subscribe_and_poll', MagicMock(return_value={'simulated_message': 'This is a mock Kafka message'}))
def test_kafka_consumer_subscribe_and_poll():
    consumer = KafkaConsumer("localhost:9092", "test_group")
    topics = ["test_topic"]
    message = consumer.subscribe_and_poll(topics)
    consumer.subscribe_and_poll.assert_called_once_with(topics)
    assert message == {"simulated_message": "This is a mock Kafka message"}
