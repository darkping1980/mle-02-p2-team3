"""공통 Neo4j 드라이버 생성의 TLS 설정을 검증하는 오프라인 테스트. 서버에 연결하지 않는다."""

import os
import unittest
from unittest.mock import Mock, patch

import certifi
from neo4j import TrustCustomCAs

from common import neo4j_connection
from common.neo4j_connection import CA_FILE_ENV_NAME, create_neo4j_driver, driver_arguments, trusted_ca_file


class DriverArgumentsTests(unittest.TestCase):
    def test_verified_schemes_keep_tls_with_explicit_ca_bundle(self):
        for uri, expected in (("neo4j+s://h:7687", "neo4j://h:7687"), ("bolt+s://h", "bolt://h"), ("NEO4J+S://h", "neo4j://h")):
            with self.subTest(uri=uri), patch.dict(os.environ, {CA_FILE_ENV_NAME: ""}):
                target, settings = driver_arguments(uri)
                self.assertEqual(target, expected)
                self.assertIs(settings["encrypted"], True)
                self.assertIsInstance(settings["trusted_certificates"], TrustCustomCAs)
                self.assertEqual(list(settings["trusted_certificates"].certs), [certifi.where()])

    def test_schemes_without_certificate_check_are_rejected(self):
        for uri in ("neo4j+ssc://h", "bolt+ssc://h"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                driver_arguments(uri)

    def test_local_schemes_stay_unchanged(self):
        for uri in ("neo4j://localhost:7687", "bolt://localhost"):
            with self.subTest(uri=uri):
                self.assertEqual(driver_arguments(uri), (uri, {}))

    def test_uri_without_scheme_is_rejected(self):
        with self.assertRaises(ValueError):
            driver_arguments("localhost")

    def test_missing_ca_file_is_an_error(self):
        with patch.dict(os.environ, {CA_FILE_ENV_NAME: "Z:/no/such/ca.pem"}), self.assertRaises(FileNotFoundError):
            trusted_ca_file()


class CreateDriverTests(unittest.TestCase):
    def test_missing_settings_name_only_the_variables(self):
        with patch.dict(os.environ, {"NEO4J_URI": "", "NEO4J_USERNAME": "", "NEO4J_PASSWORD": ""}), \
             patch.object(neo4j_connection, "load_project_environment"), \
             self.assertRaisesRegex(ValueError, "NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD"):
            create_neo4j_driver()

    def test_driver_receives_converted_uri_and_auth(self):
        with patch.dict(os.environ, {"NEO4J_URI": "neo4j://h", "NEO4J_USERNAME": "u", "NEO4J_PASSWORD": "p"}), \
             patch.object(neo4j_connection, "load_project_environment"), \
             patch("neo4j.GraphDatabase.driver", Mock(return_value="driver")) as driver:
            self.assertEqual(create_neo4j_driver(), "driver")
        driver.assert_called_once_with("neo4j://h", auth=("u", "p"))


if __name__ == "__main__":
    unittest.main()
