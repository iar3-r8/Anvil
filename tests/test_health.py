"""Tests for anvilkit.health - checking the llama-swap gateway over HTTP.

Written before the implementation (TDD step 6).

Replaces the pipeline at ``anvil:229``, which faked a JSON parser with
``curl -s | grep -o '"id":[^,]*' | sed 's/"id"://;s/"//g;s/ //g'`` and then
cross-referenced ``/running`` with a bare ``grep -q``.

Two defects of that approach are pinned down here as regression tests:

* ``grep -q "$model_name"`` matched by **substring**, so ``vendor/model-a`` was
  reported ACTIVE & HOT merely because ``vendor/model-a-instruct`` happened to be
  loaded. See ``test_hot_matching_is_exact_not_substring``.
* ``grep -o '"id":[^,]*'`` matched *any* ``id`` field anywhere in the document,
  including nested ones that are not model ids at all.

No test performs real network I/O: ``urllib.request.urlopen`` is always patched.
"""

import io
import json
import socket
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import health  # noqa: E402

PORT = 8000
MODELS_URL = "http://localhost:8000/v1/models"
RUNNING_URL = "http://localhost:8000/running"


class FakeResponse:
    """Minimal stand-in for the object urlopen returns."""

    def __init__(self, body, status=200):
        if not isinstance(body, bytes):
            body = body.encode("utf-8")
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def json_response(payload, status=200):
    return FakeResponse(json.dumps(payload), status=status)


def registry(*model_ids):
    return {"object": "list", "data": [{"id": mid} for mid in model_ids]}


def running(*model_ids):
    return {"running": [{"model": mid, "state": "ready"} for mid in model_ids]}


def responder(models_result, running_result=None):
    """Build a urlopen side effect that dispatches on the requested URL.

    Each result may be a FakeResponse or an exception instance to raise.
    """

    def side_effect(url, timeout=None):
        result = models_result if "/v1/models" in url else running_result
        if isinstance(result, BaseException):
            raise result
        if result is None:
            raise AssertionError("unexpected request to {}".format(url))
        return result

    return side_effect


class CheckGatewayOnlineTests(unittest.TestCase):
    """The happy paths."""

    def test_reports_online_when_registry_responds(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(json_response(registry("a")), json_response(running())),
        ):
            status = health.check_gateway(PORT)

        self.assertTrue(status.online)
        self.assertEqual(status.port, PORT)
        self.assertIsNone(status.error)

    def test_lists_every_registered_model(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(
                json_response(registry("coder", "embedder", "chat")),
                json_response(running("embedder")),
            ),
        ):
            status = health.check_gateway(PORT)

        self.assertEqual([m.id for m in status.models], ["coder", "embedder", "chat"])

    def test_marks_running_models_hot_and_others_cold(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(
                json_response(registry("coder", "embedder")),
                json_response(running("coder")),
            ),
        ):
            status = health.check_gateway(PORT)

        hot = {m.id: m.hot for m in status.models}
        self.assertEqual(hot, {"coder": True, "embedder": False})

    def test_requests_the_expected_urls(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(json_response(registry("a")), json_response(running())),
        ) as urlopen:
            health.check_gateway(PORT)

        requested = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(requested, [MODELS_URL, RUNNING_URL])

    def test_passes_an_explicit_timeout(self):
        """The old code used 'curl --max-time 2'; a bare urlopen would hang."""
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(json_response(registry("a")), json_response(running())),
        ) as urlopen:
            health.check_gateway(PORT)

        for call in urlopen.call_args_list:
            self.assertEqual(call.kwargs.get("timeout"), health.DEFAULT_TIMEOUT)

    def test_timeout_is_overridable(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(json_response(registry("a")), json_response(running())),
        ) as urlopen:
            health.check_gateway(PORT, timeout=0.25)

        for call in urlopen.call_args_list:
            self.assertEqual(call.kwargs.get("timeout"), 0.25)

    def test_honours_a_non_default_port(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = responder(
                json_response(registry("a")), json_response(running())
            )
            status = health.check_gateway(9999)

        self.assertEqual(status.port, 9999)
        self.assertIn("localhost:9999", urlopen.call_args_list[0].args[0])


class ExactMatchingTests(unittest.TestCase):
    """Regression tests for the substring bug in 'grep -q' at anvil:243."""

    def test_hot_matching_is_exact_not_substring(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(
                json_response(registry("vendor/model-a", "vendor/model-a-instruct")),
                json_response(running("vendor/model-a-instruct")),
            ),
        ):
            status = health.check_gateway(PORT)

        hot = {m.id: m.hot for m in status.models}
        self.assertEqual(
            hot,
            {"vendor/model-a": False, "vendor/model-a-instruct": True},
            "a loaded 'model-a-instruct' must not make 'model-a' look hot",
        )

    def test_regex_metacharacters_in_ids_are_literal(self):
        """'grep' would have treated '.' and '+' as a pattern."""
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(
                json_response(registry("qwen3.6-coder", "qwen316-coder")),
                json_response(running("qwen316-coder")),
            ),
        ):
            status = health.check_gateway(PORT)

        hot = {m.id: m.hot for m in status.models}
        self.assertEqual(hot, {"qwen3.6-coder": False, "qwen316-coder": True})

    def test_ignores_id_fields_outside_the_registry_list(self):
        """'grep -o' scraped every "id" in the document, nested or not."""
        payload = {
            "object": "list",
            "data": [{"id": "real-model", "owned_by": {"id": "not-a-model"}}],
        }
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(json_response(payload), json_response(running())),
        ):
            status = health.check_gateway(PORT)

        self.assertEqual([m.id for m in status.models], ["real-model"])


class RunningPayloadShapeTests(unittest.TestCase):
    """/running is tolerated in every shape llama-swap has been seen to emit."""

    def _hot_ids(self, running_payload):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(
                json_response(registry("coder", "embedder")),
                json_response(running_payload),
            ),
        ):
            status = health.check_gateway(PORT)
        return {m.id for m in status.models if m.hot}

    def test_wrapped_object_with_running_key(self):
        self.assertEqual(
            self._hot_ids({"running": [{"model": "coder"}]}), {"coder"}
        )

    def test_bare_list_of_objects(self):
        self.assertEqual(self._hot_ids([{"model": "coder"}]), {"coder"})

    def test_bare_list_of_strings(self):
        self.assertEqual(self._hot_ids(["coder"]), {"coder"})

    def test_objects_keyed_by_id_instead_of_model(self):
        self.assertEqual(self._hot_ids([{"id": "embedder"}]), {"embedder"})

    def test_empty_running_list_means_everything_is_cold(self):
        self.assertEqual(self._hot_ids([]), set())

    def test_unrecognised_shape_leaves_models_cold_without_raising(self):
        self.assertEqual(self._hot_ids({"unexpected": "shape"}), set())


class GatewayFailureTests(unittest.TestCase):
    """Everything that can go wrong reaching /v1/models."""

    def _offline(self, exc):
        with mock.patch("urllib.request.urlopen", side_effect=exc):
            return health.check_gateway(PORT)

    def test_connection_refused_reports_offline(self):
        status = self._offline(urllib.error.URLError(ConnectionRefusedError(111, "refused")))

        self.assertFalse(status.online)
        self.assertEqual(status.models, [])
        self.assertIsNotNone(status.error)

    def test_timeout_reports_offline(self):
        status = self._offline(socket.timeout("timed out"))

        self.assertFalse(status.online)
        self.assertIn("time", status.error.lower())

    def test_timeout_wrapped_in_urlerror_reports_offline(self):
        status = self._offline(urllib.error.URLError(socket.timeout("timed out")))

        self.assertFalse(status.online)
        self.assertIsNotNone(status.error)

    def test_http_error_reports_offline_with_the_status_code(self):
        status = self._offline(
            urllib.error.HTTPError(MODELS_URL, 503, "Service Unavailable", {}, None)
        )

        self.assertFalse(status.online)
        self.assertIn("503", status.error)

    def test_os_error_reports_offline(self):
        status = self._offline(OSError("network unreachable"))

        self.assertFalse(status.online)
        self.assertIsNotNone(status.error)

    def test_offline_check_does_not_query_running(self):
        with mock.patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("down")
        ) as urlopen:
            health.check_gateway(PORT)

        self.assertEqual(len(urlopen.call_args_list), 1)


class RegistryPayloadTests(unittest.TestCase):
    """A reachable gateway can still return a body we cannot use."""

    def _status(self, models_response):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(models_response, json_response(running())),
        ):
            return health.check_gateway(PORT)

    def test_non_json_body_is_reported_as_an_unreadable_registry(self):
        status = self._status(FakeResponse("<html>gateway error</html>"))

        self.assertTrue(status.online)
        self.assertEqual(status.models, [])
        self.assertIsNotNone(status.registry_error)

    def test_empty_registry_is_online_with_no_models(self):
        status = self._status(json_response(registry()))

        self.assertTrue(status.online)
        self.assertEqual(status.models, [])
        self.assertIsNone(status.registry_error)

    def test_missing_data_key_is_reported_as_an_unreadable_registry(self):
        status = self._status(json_response({"object": "list"}))

        self.assertTrue(status.online)
        self.assertEqual(status.models, [])
        self.assertIsNotNone(status.registry_error)

    def test_entries_without_an_id_are_skipped(self):
        payload = {"data": [{"id": "good"}, {"object": "model"}, {"id": ""}]}
        status = self._status(json_response(payload))

        self.assertEqual([m.id for m in status.models], ["good"])

    def test_data_that_is_not_a_list_is_reported_as_unreadable(self):
        status = self._status(json_response({"data": "not-a-list"}))

        self.assertTrue(status.online)
        self.assertEqual(status.models, [])
        self.assertIsNotNone(status.registry_error)

    def test_top_level_list_registry_is_accepted(self):
        status = self._status(json_response([{"id": "coder"}]))

        self.assertEqual([m.id for m in status.models], ["coder"])


class RunningFailureTests(unittest.TestCase):
    """/running may fail while /v1/models succeeds."""

    def _status(self, running_result):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=responder(json_response(registry("coder")), running_result),
        ):
            return health.check_gateway(PORT)

    def test_gateway_stays_online_when_running_errors(self):
        status = self._status(urllib.error.URLError("boom"))

        self.assertTrue(status.online)
        self.assertEqual([m.id for m in status.models], ["coder"])

    def test_models_are_reported_cold_when_running_errors(self):
        status = self._status(urllib.error.URLError("boom"))

        self.assertFalse(status.models[0].hot)

    def test_running_error_is_recorded(self):
        status = self._status(urllib.error.HTTPError(RUNNING_URL, 404, "nope", {}, None))

        self.assertIsNotNone(status.running_error)
        self.assertIn("404", status.running_error)

    def test_non_json_running_body_is_recorded_not_raised(self):
        status = self._status(FakeResponse("not json at all"))

        self.assertTrue(status.online)
        self.assertIsNotNone(status.running_error)
        self.assertFalse(status.models[0].hot)


class FormatStatusTests(unittest.TestCase):
    """Human-readable output must preserve the wording from anvil:244."""

    def _online(self, models=(("coder", True), ("embedder", False)), **kwargs):
        return health.GatewayStatus(
            port=PORT,
            online=True,
            models=[health.ModelStatus(mid, hot) for mid, hot in models],
            **kwargs
        )

    def test_offline_wording_is_preserved(self):
        text = health.format_status(
            health.GatewayStatus(port=PORT, online=False, error="refused"),
            use_color=False,
        )

        self.assertIn("OFFLINE", text)
        self.assertIn("Swap Router Gateway", text)
        self.assertIn(str(PORT), text)

    def test_online_wording_is_preserved(self):
        text = health.format_status(self._online(), use_color=False)

        self.assertIn("ONLINE & ROUTING", text)

    def test_hot_and_cold_wording_is_preserved(self):
        text = health.format_status(self._online(), use_color=False)

        self.assertIn("ACTIVE & HOT", text)
        self.assertIn("COLD", text)
        self.assertIn("coder", text)
        self.assertIn("embedder", text)

    def test_empty_registry_warning_is_preserved(self):
        text = health.format_status(self._online(models=()), use_color=False)

        self.assertIn("No models returned", text)

    def test_no_color_output_contains_no_escape_sequences(self):
        text = health.format_status(self._online(), use_color=False)

        self.assertNotIn("\033", text)

    def test_color_output_contains_escape_sequences(self):
        text = health.format_status(self._online(), use_color=True)

        self.assertIn("\033", text)

    def test_color_and_plain_output_carry_the_same_words(self):
        plain = health.format_status(self._online(), use_color=False)
        colored = health.format_status(self._online(), use_color=True)

        self.assertEqual(
            plain.replace(" ", ""),
            _strip_ansi(colored).replace(" ", ""),
        )

    def test_registry_error_is_surfaced(self):
        text = health.format_status(
            self._online(models=(), registry_error="malformed payload"),
            use_color=False,
        )

        self.assertIn("malformed payload", text)

    def test_running_error_is_surfaced(self):
        text = health.format_status(
            self._online(running_error="404"), use_color=False
        )

        self.assertIn("404", text)

    def test_offline_output_lists_no_models(self):
        text = health.format_status(
            health.GatewayStatus(port=PORT, online=False, error="refused"),
            use_color=False,
        )

        self.assertNotIn("ACTIVE & HOT", text)


class FormatJsonTests(unittest.TestCase):
    """--json output must be machine-readable."""

    def test_output_is_valid_json(self):
        status = health.GatewayStatus(
            port=PORT,
            online=True,
            models=[health.ModelStatus("coder", True)],
        )

        self.assertEqual(
            json.loads(health.format_json(status))["port"], PORT
        )

    def test_models_carry_id_and_hot_flag(self):
        status = health.GatewayStatus(
            port=PORT,
            online=True,
            models=[health.ModelStatus("coder", True), health.ModelStatus("e", False)],
        )

        data = json.loads(health.format_json(status))

        self.assertEqual(
            data["models"],
            [{"id": "coder", "hot": True}, {"id": "e", "hot": False}],
        )

    def test_offline_status_serialises_its_error(self):
        status = health.GatewayStatus(port=PORT, online=False, error="refused")

        data = json.loads(health.format_json(status))

        self.assertFalse(data["online"])
        self.assertEqual(data["error"], "refused")
        self.assertEqual(data["models"], [])

    def test_json_contains_no_ansi_escapes(self):
        status = health.GatewayStatus(
            port=PORT, online=True, models=[health.ModelStatus("coder", True)]
        )

        self.assertNotIn("\033", health.format_json(status))


# ---------------------------------------------------------------------------
# test_model - sending a real prompt through the gateway
# ---------------------------------------------------------------------------

CHAT_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "vendor/coder"
PROMPT = "say pong"


def chat_completion(
    content="pong", reasoning=None, prompt_tokens=11, completion_tokens=2
):
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning

    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": MODEL,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _requested_url(target):
    """urlopen is handed a str for the registry GET and a Request for the POST."""
    return target if isinstance(target, str) else target.full_url


def probe_responder(models_result, chat_result=None):
    """Dispatch on the requested URL, as ``responder`` does for check_gateway."""

    def side_effect(target, timeout=None):
        url = _requested_url(target)
        result = models_result if "/v1/models" in url else chat_result
        if isinstance(result, BaseException):
            raise result
        if result is None:
            raise AssertionError("unexpected request to {}".format(url))
        return result

    return side_effect


def http_error(code, body="", url=CHAT_URL):
    return urllib.error.HTTPError(
        url, code, "Bad Request", {}, io.BytesIO(body.encode("utf-8"))
    )


def sent_body(urlopen):
    """The JSON body of the POST the code under test issued."""
    for call in urlopen.call_args_list:
        target = call.args[0]
        if not isinstance(target, str):
            return json.loads(target.data.decode("utf-8"))
    raise AssertionError("no POST was sent")


def sent_request(urlopen):
    for call in urlopen.call_args_list:
        target = call.args[0]
        if not isinstance(target, str):
            return target
    raise AssertionError("no POST was sent")


class FakeClock:
    """A monotonic clock stub that never runs out of readings."""

    def __init__(self, *readings):
        self._readings = list(readings)

    def __call__(self):
        if len(self._readings) > 1:
            return self._readings.pop(0)
        return self._readings[0]


class TestModelSuccessTests(unittest.TestCase):
    """A model that answers is reported as a pass, with what it said."""

    def _run(self, response=None, **kwargs):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=probe_responder(
                json_response(registry(MODEL)),
                json_response(response if response is not None else chat_completion()),
            ),
        ):
            return health.test_model(PORT, MODEL, prompt=PROMPT, **kwargs)

    def test_reports_ok_when_the_model_replies(self):
        self.assertTrue(self._run().ok)

    def test_records_the_reply_text(self):
        self.assertEqual("pong", self._run().reply)

    def test_records_no_error_on_success(self):
        self.assertIsNone(self._run().error)

    def test_echoes_back_the_model_and_prompt(self):
        result = self._run()

        self.assertEqual(MODEL, result.model_id)
        self.assertEqual(PROMPT, result.prompt)
        self.assertEqual(PORT, result.port)

    def test_records_token_usage(self):
        result = self._run(chat_completion(prompt_tokens=7, completion_tokens=3))

        self.assertEqual(7, result.prompt_tokens)
        self.assertEqual(3, result.completion_tokens)

    def test_missing_usage_leaves_the_counts_unset(self):
        payload = chat_completion()
        del payload["usage"]

        result = self._run(payload)

        self.assertTrue(result.ok)
        self.assertIsNone(result.prompt_tokens)
        self.assertIsNone(result.completion_tokens)

    def test_measures_the_latency_of_the_completion(self):
        with mock.patch("time.monotonic", FakeClock(10.0, 11.5)):
            result = self._run()

        self.assertAlmostEqual(1.5, result.latency_seconds, places=3)

    def test_a_reasoning_model_answering_only_in_reasoning_content_still_passes(self):
        """vLLM's qwen3 reasoning parser can leave 'content' empty."""
        result = self._run(chat_completion(content="", reasoning="pong"))

        self.assertTrue(result.ok)
        self.assertEqual("pong", result.reply)


class TestModelRequestTests(unittest.TestCase):
    """What is actually put on the wire."""

    def _run(self, **kwargs):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=probe_responder(
                json_response(registry(MODEL)), json_response(chat_completion())
            ),
        ) as urlopen:
            health.test_model(PORT, MODEL, prompt=PROMPT, **kwargs)
        return urlopen

    def test_reads_the_registry_before_prompting(self):
        urlopen = self._run()

        self.assertEqual(MODELS_URL, _requested_url(urlopen.call_args_list[0].args[0]))

    def test_posts_to_the_chat_completions_endpoint(self):
        self.assertEqual(CHAT_URL, sent_request(self._run()).full_url)

    def test_uses_the_post_method(self):
        self.assertEqual("POST", sent_request(self._run()).get_method())

    def test_declares_a_json_content_type(self):
        request = sent_request(self._run())

        self.assertEqual("application/json", request.get_header("Content-type"))

    def test_sends_the_model_and_the_prompt(self):
        body = sent_body(self._run())

        self.assertEqual(MODEL, body["model"])
        self.assertEqual([{"role": "user", "content": PROMPT}], body["messages"])

    def test_sends_the_requested_token_ceiling(self):
        self.assertEqual(12, sent_body(self._run(max_tokens=12))["max_tokens"])

    def test_does_not_stream(self):
        self.assertFalse(sent_body(self._run())["stream"])

    def test_registry_lookup_uses_the_short_status_timeout(self):
        """An unreachable gateway must still fail fast, as 'status' does."""
        urlopen = self._run()

        self.assertEqual(
            health.DEFAULT_TIMEOUT, urlopen.call_args_list[0].kwargs.get("timeout")
        )

    def test_generation_uses_the_long_timeout(self):
        """A cold model is loaded on demand, so the answer can be minutes away."""
        urlopen = self._run()

        post = [
            call
            for call in urlopen.call_args_list
            if not isinstance(call.args[0], str)
        ][0]
        self.assertEqual(
            health.DEFAULT_GENERATION_TIMEOUT, post.kwargs.get("timeout")
        )

    def test_generation_timeout_is_overridable(self):
        urlopen = self._run(timeout=5.0)

        post = [
            call
            for call in urlopen.call_args_list
            if not isinstance(call.args[0], str)
        ][0]
        self.assertEqual(5.0, post.kwargs.get("timeout"))

    def test_honours_a_non_default_port(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=probe_responder(
                json_response(registry(MODEL)), json_response(chat_completion())
            ),
        ) as urlopen:
            result = health.test_model(9999, MODEL, prompt=PROMPT)

        self.assertEqual(9999, result.port)
        self.assertIn("localhost:9999", sent_request(urlopen).full_url)


class TestModelFailureTests(unittest.TestCase):
    """Every failure is reported, and none of them raise."""

    def _run(self, models_result, chat_result=None, **kwargs):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=probe_responder(models_result, chat_result),
        ):
            return health.test_model(PORT, MODEL, prompt=PROMPT, **kwargs)

    def test_an_unknown_model_is_rejected_before_any_prompt_is_sent(self):
        # chat_result is None, so the responder raises if a POST is attempted.
        result = self._run(json_response(registry("vendor/other")))

        self.assertFalse(result.ok)
        self.assertTrue(result.unknown_model)

    def test_an_unknown_model_reports_what_is_registered(self):
        result = self._run(json_response(registry("vendor/other", "vendor/third")))

        self.assertEqual(["vendor/other", "vendor/third"], result.available_models)

    def test_the_unknown_model_error_names_the_model(self):
        result = self._run(json_response(registry("vendor/other")))

        self.assertIn(MODEL, result.error)

    def test_registry_matching_is_exact_not_substring(self):
        """'vendor/coder-instruct' being registered must not accept 'vendor/coder'."""
        result = self._run(json_response(registry(MODEL + "-instruct")))

        self.assertFalse(result.ok)
        self.assertTrue(result.unknown_model)

    def test_an_offline_gateway_is_reported(self):
        result = self._run(urllib.error.URLError("connection refused"))

        self.assertFalse(result.ok)
        self.assertIn("connection refused", result.error)

    def test_an_offline_gateway_is_not_an_unknown_model(self):
        result = self._run(urllib.error.URLError("connection refused"))

        self.assertFalse(result.unknown_model)

    def test_an_http_error_from_the_gateway_is_reported(self):
        result = self._run(json_response(registry(MODEL)), http_error(500))

        self.assertFalse(result.ok)
        self.assertIn("500", result.error)

    def test_the_gateway_error_body_is_surfaced(self):
        """An embedding model cannot answer a chat completion; say why."""
        body = json.dumps(
            {"error": {"message": "This model does not support chat completions"}}
        )
        result = self._run(json_response(registry(MODEL)), http_error(400, body))

        self.assertIn("does not support chat completions", result.error)

    def test_a_plain_text_error_body_is_surfaced(self):
        result = self._run(
            json_response(registry(MODEL)), http_error(503, "no healthy upstream")
        )

        self.assertIn("no healthy upstream", result.error)

    def test_a_generation_timeout_is_reported(self):
        result = self._run(
            json_response(registry(MODEL)), socket.timeout("timed out"), timeout=7.0
        )

        self.assertFalse(result.ok)
        self.assertIn("timed out", result.error)
        self.assertIn("7.0", result.error)

    def test_a_non_json_completion_body_is_reported(self):
        result = self._run(json_response(registry(MODEL)), FakeResponse("not json"))

        self.assertFalse(result.ok)
        self.assertIn("JSON", result.error)

    def test_a_completion_without_choices_is_reported(self):
        result = self._run(
            json_response(registry(MODEL)), json_response({"choices": []})
        )

        self.assertFalse(result.ok)
        self.assertIn("choices", result.error)

    def test_an_empty_reply_is_a_failure(self):
        result = self._run(
            json_response(registry(MODEL)), json_response(chat_completion(content="   "))
        )

        self.assertFalse(result.ok)
        self.assertIn("empty", result.error)

    def test_a_reply_truncated_by_the_token_limit_says_so(self):
        """Distinguish 'ran out of budget' from 'answered with nothing'."""
        payload = chat_completion(content="")
        payload["choices"][0]["finish_reason"] = "length"

        result = self._run(json_response(registry(MODEL)), json_response(payload))

        self.assertFalse(result.ok)
        self.assertIn("token limit", result.error)
        self.assertIn("--max-tokens", result.error)

    def test_an_unreadable_registry_is_reported(self):
        result = self._run(FakeResponse("not json"))

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)


class FormatModelTestTests(unittest.TestCase):
    """The human report, kept separate from the probe that produced it."""

    def _passed(self, **kwargs):
        defaults = dict(
            port=PORT,
            model_id=MODEL,
            prompt=PROMPT,
            ok=True,
            reply="pong",
            latency_seconds=1.5,
            prompt_tokens=11,
            completion_tokens=2,
        )
        defaults.update(kwargs)
        return health.ModelTestResult(**defaults)

    def _failed(self, **kwargs):
        defaults = dict(
            port=PORT, model_id=MODEL, prompt=PROMPT, ok=False, error="refused"
        )
        defaults.update(kwargs)
        return health.ModelTestResult(**defaults)

    def test_a_pass_is_announced(self):
        self.assertIn("PASS", health.format_model_test(self._passed(), use_color=False))

    def test_a_pass_shows_the_reply(self):
        self.assertIn("pong", health.format_model_test(self._passed(), use_color=False))

    def test_a_pass_shows_the_model_and_port(self):
        text = health.format_model_test(self._passed(), use_color=False)

        self.assertIn(MODEL, text)
        self.assertIn(str(PORT), text)

    def test_a_pass_shows_the_latency(self):
        self.assertIn("1.50", health.format_model_test(self._passed(), use_color=False))

    def test_a_pass_shows_the_token_counts(self):
        text = health.format_model_test(self._passed(), use_color=False)

        self.assertIn("11", text)
        self.assertIn("2", text)

    def test_a_failure_is_announced(self):
        self.assertIn("FAIL", health.format_model_test(self._failed(), use_color=False))

    def test_a_failure_shows_the_error(self):
        self.assertIn(
            "refused", health.format_model_test(self._failed(), use_color=False)
        )

    def test_a_failure_never_claims_a_pass(self):
        self.assertNotIn(
            "PASS", health.format_model_test(self._failed(), use_color=False)
        )

    def test_an_unknown_model_lists_the_registry(self):
        text = health.format_model_test(
            self._failed(
                unknown_model=True,
                error="not registered",
                available_models=["vendor/other", "vendor/third"],
            ),
            use_color=False,
        )

        self.assertIn("vendor/other", text)
        self.assertIn("vendor/third", text)

    def test_a_generation_failure_does_not_dump_the_registry(self):
        """The registry is only useful when the name itself was wrong."""
        text = health.format_model_test(
            self._failed(available_models=["vendor/other"]), use_color=False
        )

        self.assertNotIn("vendor/other", text)

    def test_no_color_output_contains_no_escape_sequences(self):
        self.assertNotIn(
            "\033", health.format_model_test(self._passed(), use_color=False)
        )

    def test_color_output_contains_escape_sequences(self):
        self.assertIn("\033", health.format_model_test(self._passed(), use_color=True))

    def test_color_and_plain_output_carry_the_same_words(self):
        plain = health.format_model_test(self._passed(), use_color=False)
        colored = health.format_model_test(self._passed(), use_color=True)

        self.assertEqual(plain, _strip_ansi(colored))


class FormatModelTestJsonTests(unittest.TestCase):
    """--json output must be machine-readable."""

    def _result(self, **kwargs):
        defaults = dict(
            port=PORT,
            model_id=MODEL,
            prompt=PROMPT,
            ok=True,
            reply="pong",
            latency_seconds=1.5,
            prompt_tokens=11,
            completion_tokens=2,
        )
        defaults.update(kwargs)
        return health.ModelTestResult(**defaults)

    def test_output_is_valid_json(self):
        data = json.loads(health.format_model_test_json(self._result()))

        self.assertEqual(PORT, data["port"])

    def test_carries_the_outcome_and_the_reply(self):
        data = json.loads(health.format_model_test_json(self._result()))

        self.assertTrue(data["ok"])
        self.assertEqual("pong", data["reply"])
        self.assertEqual(MODEL, data["model"])
        self.assertIsNone(data["error"])

    def test_carries_the_usage_counts(self):
        data = json.loads(health.format_model_test_json(self._result()))

        self.assertEqual(
            {"prompt_tokens": 11, "completion_tokens": 2}, data["usage"]
        )

    def test_a_failure_serialises_its_error(self):
        data = json.loads(
            health.format_model_test_json(
                self._result(ok=False, reply=None, error="refused")
            )
        )

        self.assertFalse(data["ok"])
        self.assertEqual("refused", data["error"])

    def test_an_unknown_model_serialises_the_registry(self):
        data = json.loads(
            health.format_model_test_json(
                self._result(
                    ok=False,
                    reply=None,
                    error="not registered",
                    unknown_model=True,
                    available_models=["a", "b"],
                )
            )
        )

        self.assertTrue(data["unknown_model"])
        self.assertEqual(["a", "b"], data["available_models"])

    def test_json_contains_no_ansi_escapes(self):
        self.assertNotIn("\033", health.format_model_test_json(self._result()))


class FormatRequestTests(unittest.TestCase):
    """The --dry-run preview, so a request can be inspected without sending it."""

    def _body(self):
        return health.build_chat_request(MODEL, PROMPT, 32)

    def test_build_chat_request_carries_the_prompt(self):
        body = self._body()

        self.assertEqual(MODEL, body["model"])
        self.assertEqual([{"role": "user", "content": PROMPT}], body["messages"])
        self.assertEqual(32, body["max_tokens"])

    def test_build_chat_request_disables_thinking(self):
        self.assertEqual(
            {"enable_thinking": False}, self._body()["chat_template_kwargs"]
        )

    def test_human_preview_names_the_endpoint(self):
        text = health.format_request(PORT, self._body())

        self.assertIn(CHAT_URL, text)

    def test_human_preview_shows_the_prompt(self):
        self.assertIn(PROMPT, health.format_request(PORT, self._body()))

    def test_json_preview_is_valid_json(self):
        data = json.loads(health.format_request_json(PORT, self._body()))

        self.assertEqual(PORT, data["port"])
        self.assertEqual(CHAT_URL, data["url"])
        self.assertEqual(MODEL, data["body"]["model"])


def _strip_ansi(text):
    import re

    return re.sub(r"\033\[[0-9;]*m", "", text)


if __name__ == "__main__":
    unittest.main()
