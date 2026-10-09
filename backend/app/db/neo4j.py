from neo4j import GraphDatabase

from backend.app.config import settings

driver = GraphDatabase.driver(
    settings.neo4j_url,
    auth=(settings.neo4j_username, settings.neo4j_password),
)