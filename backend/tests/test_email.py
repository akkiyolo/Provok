"""Email providers."""
from __future__ import annotations

import boto3
from botocore.stub import Stubber

from backend.app.core.config import get_settings
from backend.app.services import email


def test_ses_sends_html_and_text_from_the_configured_sender(monkeypatch) -> None:
    client = boto3.client("sesv2", region_name="ap-south-1", aws_access_key_id="x", aws_secret_access_key="y")
    stub = Stubber(client)
    stub.add_response("send_email", {"MessageId": "m-1"}, {
        "FromEmailAddress": get_settings().email_from,
        "Destination": {"ToAddresses": ["nia@example.com"]},
        "Content": {"Simple": {"Subject": {"Data": "Hi", "Charset": "UTF-8"},
                               "Body": {"Text": {"Data": "plain", "Charset": "UTF-8"},
                                        "Html": {"Data": "<p>rich</p>", "Charset": "UTF-8"}}}},
    })
    regions = []
    monkeypatch.setattr(boto3, "client", lambda service, region_name=None: regions.append(region_name) or client)
    with stub:
        email._send_ses("nia@example.com", "Hi", "<p>rich</p>", "plain")
    stub.assert_no_pending_responses()
    assert regions == [get_settings().ses_region]
