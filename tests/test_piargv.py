"""Tests for anvilkit.piargv - the bake-off invocation argv builder.

Written before the implementation (TDD, ``plans/pi-phase1-bakeoff.md``,
behaviour 4: "print invocation argv" and behaviour 5: "json invocation
argv"). Behaviours 6 (ultrawork argv) and 7 (models document) will
land in later cycles as further classes in the same file.

The production module ``anvilkit.piargv`` does not exist yet, so every
test loads it through ``_piargv``, which fails with a clear assertion
instead of letting a collection-time ImportError mask the reason the
suite is red.
"""

import importlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class PiargvTestCase(unittest.TestCase):
    def _piargv(self):
        """Import anvilkit.piargv, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.piargv")
        self.assertIsNotNone(
            spec,
            "anvilkit.piargv cannot be imported; the bake-off argv "
            "builder has not been implemented yet",
        )
        return importlib.import_module("anvilkit.piargv")


class TestPrintArgv(PiargvTestCase):
    """Behaviour 4: print invocation argv.

    The pinned signature is ``print_argv(model_id, prompt)`` returning
    a ``List[str]``. The plan's "fixture path" input is intentionally
    NOT part of the signature: the argv carries no cwd or path token,
    and the host run recipe (behaviour 18) sets the subprocess cwd to
    the fixture directory separately, so baking a path into the argv
    would couple the builder to where the fixture happens to live.
    """

    def test_print_argv_returns_exact_token_list(self):
        piargv = self._piargv()
        argv = piargv.print_argv("llamaswap/coder", "Edit adder.py so add(2, 3) == 5")
        self.assertIsInstance(
            argv,
            list,
            "print_argv must return a list of tokens, never a string, "
            "so no shell re-parses it",
        )
        self.assertEqual(
            argv,
            [
                "pi",
                "-p",
                "--model",
                "llamaswap/coder",
                "--tools",
                "read,edit,write",
                "-a",
                "--no-session",
                "--",
                "Edit adder.py so add(2, 3) == 5",
            ],
        )

    def test_print_argv_prompt_is_final_element_after_double_dash(self):
        piargv = self._piargv()
        argv = piargv.print_argv("llamaswap/coder", "fix it")
        self.assertEqual(argv[-1], "fix it")
        self.assertEqual(argv[-2], "--")

    def test_print_argv_prompt_beginning_with_dash_is_included_as_is(self):
        # "--" already precedes the prompt, so a leading-dash prompt is
        # safe and must be passed through verbatim, not rejected.
        piargv = self._piargv()
        argv = piargv.print_argv("llamaswap/coder", "-p --mode json -- evil prompt")
        self.assertEqual(argv[-1], "-p --mode json -- evil prompt")
        self.assertNotIsInstance(argv, (str, bytes))

    def test_print_argv_empty_model_id_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.print_argv("", "Edit adder.py so add(2, 3) == 5")

    def test_print_argv_whitespace_model_id_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.print_argv("   ", "Edit adder.py so add(2, 3) == 5")

    def test_print_argv_empty_prompt_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.print_argv("llamaswap/coder", "")


class TestJsonArgv(PiargvTestCase):
    """Behaviour 5: json invocation argv.

    Pinned signature ``json_argv(model_id, prompt) -> List[str]``. The plan
    says the list is identical to behaviour 4's except ``-p`` replaced by
    ``--mode json``, so the drift-critical test builds ``print_argv`` in-test
    and pins the relationship instead of hardcoding both lists (which would
    let the two builders drift together).
    """

    def test_json_argv_returns_exact_token_list(self):
        piargv = self._piargv()
        argv = piargv.json_argv("llamaswap/coder", "Edit adder.py so add(2, 3) == 5")
        self.assertIsInstance(
            argv,
            list,
            "json_argv must return a list of tokens, never a string, "
            "so no shell re-parses it",
        )
        self.assertEqual(
            argv,
            [
                "pi",
                "--mode",
                "json",
                "--model",
                "llamaswap/coder",
                "--tools",
                "read,edit,write",
                "-a",
                "--no-session",
                "--",
                "Edit adder.py so add(2, 3) == 5",
            ],
        )

    def test_json_argv_identical_to_print_argv_except_harness_form(self):
        piargv = self._piargv()
        model_id = "llamaswap/coder"
        prompt = "Edit adder.py so add(2, 3) == 5"
        print_argv = piargv.print_argv(model_id, prompt)
        json_argv = piargv.json_argv(model_id, prompt)

        # The harness form sits immediately after the program name, and is
        # the only difference between the two invocations.
        self.assertEqual(json_argv[:1], ["pi"])
        self.assertEqual(print_argv[1], "-p")
        self.assertEqual(json_argv[1:3], ["--mode", "json"])
        # "-p" is one token, "--mode json" is two, so the json form is
        # exactly one token longer; every other token is element-for-element
        # equal, with "--model" onward shifted by one position.
        self.assertEqual(len(json_argv), len(print_argv) + 1)
        self.assertEqual(
            json_argv[3:],
            print_argv[2:],
            "every token after the harness form must be equal "
            "element-for-element; only the harness form may differ",
        )

    def test_json_argv_empty_model_id_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.json_argv("", "Edit adder.py so add(2, 3) == 5")

    def test_json_argv_whitespace_model_id_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.json_argv("   ", "Edit adder.py so add(2, 3) == 5")

    def test_json_argv_empty_prompt_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.json_argv("llamaswap/coder", "")


class TestUltraworkArgv(PiargvTestCase):
    """Behaviour 6: ultrawork invocation argv.

    Pinned signature ``ultrawork_argv(model_id, prompt, extension_path)``
    returning a ``List[str]``. Unlike the fixture cwd, the extension path is a
    real argv token (``-e <path>``), so it is in the signature
    (``doc/external/pi-dev/cli.md``, Resources: ``-e``/``--extension`` loads an
    extension file or directory).

    Pinned prompt prefix format: when the given prompt does not contain
    ``ultrawork`` as a whole word, the emitted prompt element is exactly
    ``"ultrawork " + prompt`` — the trigger word, one space, then the original
    prompt verbatim. When the prompt already contains the whole word, it is
    passed through unchanged. Rationale: the plan's interface fact is that the
    trigger is the whole word ``ultrawork`` (``doc/external/pi-dev/packages/pi-ultrawork.md``:
    "say ``ultrawork`` or ``ulw`` (as a whole word)"; plan behaviour 16 records
    the trigger as ``\\b(ultrawork|ulw)\\b``), and behaviour 6 requires the
    prompt's first word to be ``ultrawork`` so the trigger fires. One space is
    the minimal separator that keeps the trigger a whole word without
    mutating the original prompt.
    """

    def test_ultrawork_argv_returns_exact_token_list(self):
        piargv = self._piargv()
        argv = piargv.ultrawork_argv(
            "llamaswap/coder",
            "Edit adder.py so add(2, 3) == 5",
            "./pi-ultrawork",
        )
        self.assertIsInstance(
            argv,
            list,
            "ultrawork_argv must return a list of tokens, never a string, "
            "so no shell re-parses it",
        )
        self.assertEqual(
            argv,
            [
                "pi",
                "-p",
                "-e",
                "./pi-ultrawork",
                "--model",
                "llamaswap/coder",
                "--tools",
                "read,edit,write,ulw_dispatch,ulw_complete",
                "-a",
                "--no-session",
                "--",
                "ultrawork Edit adder.py so add(2, 3) == 5",
            ],
        )

    def test_ultrawork_argv_extension_path_is_included_verbatim_after_harness_form(self):
        piargv = self._piargv()
        ext = "/home/user/packages/pi-ultrawork/src/index.ts"
        argv = piargv.ultrawork_argv("llamaswap/coder", "fix it", ext)
        self.assertEqual(
            argv[1:4],
            ["-p", "-e", ext],
            "the extension path must be a real argv token via -e, "
            "included verbatim immediately after the harness form",
        )
        self.assertEqual(argv[-1], "ultrawork fix it")

    def test_ultrawork_argv_prompt_without_trigger_is_prefixed_once(self):
        piargv = self._piargv()
        prompt = "Edit adder.py so add(2, 3) == 5"
        argv = piargv.ultrawork_argv("llamaswap/coder", prompt, "./pi-ultrawork")
        emitted = argv[-1]
        self.assertTrue(
            emitted.startswith("ultrawork "),
            "the emitted prompt must begin with the whole word 'ultrawork' "
            "so the extension's whole-word trigger fires",
        )
        self.assertEqual(
            emitted,
            "ultrawork " + prompt,
            "the prefix must be 'ultrawork ' exactly once, with the "
            "original prompt following verbatim",
        )

    def test_ultrawork_argv_prompt_already_containing_trigger_is_not_prefixed(self):
        piargv = self._piargv()
        prompt = "ultrawork: edit adder.py so add(2, 3) == 5"
        argv = piargv.ultrawork_argv("llamaswap/coder", prompt, "./pi-ultrawork")
        self.assertEqual(
            argv[-1],
            prompt,
            "a prompt that already contains the whole word 'ultrawork' "
            "must pass through unchanged, never prefixed twice",
        )
        self.assertEqual(argv[-1].count("ultrawork"), 1)

    def test_ultrawork_argv_trigger_match_is_whole_word_only(self):
        # 'ultraworking' contains the trigger as a substring, not as a whole
        # word, so the trigger does not fire and the prompt IS prefixed
        # (plan behaviour 16: the trigger is \b(ultrawork|ulw)\b).
        piargv = self._piargv()
        prompt = "I was ultraworking on this yesterday"
        argv = piargv.ultrawork_argv("llamaswap/coder", prompt, "./pi-ultrawork")
        self.assertEqual(argv[-1], "ultrawork " + prompt)

    def test_ultrawork_argv_differs_from_print_argv_by_extension_tools_and_prompt(self):
        piargv = self._piargv()
        model_id = "llamaswap/coder"
        prompt = "Edit adder.py so add(2, 3) == 5"
        ext = "./pi-ultrawork"
        print_argv = piargv.print_argv(model_id, prompt)
        uw_argv = piargv.ultrawork_argv(model_id, prompt, ext)

        # The only extra tokens are the -e <path> pair right after the
        # harness form; with them removed the two invocations have equal
        # length.
        self.assertEqual(uw_argv[1:4], ["-p", "-e", ext])
        aligned = uw_argv[:2] + uw_argv[4:]
        self.assertEqual(len(aligned), len(print_argv))
        # Exactly two positions may differ: the --tools value (the ulw pair is
        # added to the print selection) and the final prompt (prefixed with
        # the trigger word). Every other token must stay element-for-element.
        diffs = [
            i
            for i, (a, b) in enumerate(zip(aligned, print_argv))
            if a != b
        ]
        self.assertEqual(diffs, [5, len(print_argv) - 1])
        self.assertEqual(
            aligned[5],
            "read,edit,write,ulw_dispatch,ulw_complete",
        )

    def test_ultrawork_argv_empty_extension_path_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.ultrawork_argv("llamaswap/coder", "fix it", "")

    def test_ultrawork_argv_whitespace_extension_path_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.ultrawork_argv("llamaswap/coder", "fix it", "   ")

    def test_ultrawork_argv_empty_model_id_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.ultrawork_argv("", "fix it", "./pi-ultrawork")

    def test_ultrawork_argv_whitespace_model_id_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.ultrawork_argv("   ", "fix it", "./pi-ultrawork")

    def test_ultrawork_argv_empty_prompt_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.ultrawork_argv("llamaswap/coder", "", "./pi-ultrawork")


class TestModelsDocument(PiargvTestCase):
    """Behaviour 7: models document.

    Pinned signature ``models_document(model_id, port, context_window,
    max_tokens) -> dict``. ``max_tokens`` is a parameter rather than a hidden
    default because Pi defaults ``maxTokens`` to 16384 and ``contextWindow``
    to 128000, and long-context local models must override both, so the
    document carries the explicit values (``doc/external/pi-dev/
    models-configuration.md``, Models).

    The dummy apiKey is pinned to ``"llamaswap-local"``: Pi needs a non-empty
    string and the local llama-swap gateway ignores it, exactly as the
    Ollama example shows (``doc/external/pi-dev/models.md``, Configure a
    compatible endpoint: "The dummy key makes the model available to Pi;
    Ollama ignores it").
    """

    def test_models_document_returns_exact_dict_shape(self):
        piargv = self._piargv()
        doc = piargv.models_document("llamaswap/coder", 1234, 131072, 16384)
        self.assertIsInstance(
            doc,
            dict,
            "models_document must return a dict to feed json.dumps, "
            "never a hand-built JSON string",
        )
        self.assertEqual(
            doc,
            {
                "providers": {
                    "llamaswap": {
                        "baseUrl": "http://127.0.0.1:1234/v1",
                        "api": "openai-completions",
                        "apiKey": "llamaswap-local",
                        "models": [
                            {
                                "id": "llamaswap/coder",
                                "contextWindow": 131072,
                                "maxTokens": 16384,
                            }
                        ],
                    }
                }
            },
        )

    def test_models_document_interpolates_model_id_port_and_windows_not_hardcoded(self):
        piargv = self._piargv()
        doc = piargv.models_document("llamaswap/other", 8080, 32768, 4096)
        provider = doc["providers"]["llamaswap"]
        self.assertEqual(
            provider["baseUrl"],
            "http://127.0.0.1:8080/v1",
            "the port must be interpolated into the baseUrl, "
            "never left as a template like <port>",
        )
        entry = provider["models"][0]
        self.assertEqual(entry["id"], "llamaswap/other")
        self.assertEqual(entry["contextWindow"], 32768)
        self.assertEqual(
            entry["maxTokens"],
            4096,
            "maxTokens must be the explicit argument, not Pi's 16384 default",
        )
        self.assertNotIn("<", provider["baseUrl"])

    def test_models_document_is_json_dumps_round_trip(self):
        piargv = self._piargv()
        doc = piargv.models_document("llamaswap/coder", 1234, 131072, 16384)
        serialized = json.dumps(doc, sort_keys=True)
        self.assertEqual(
            json.loads(serialized),
            doc,
            "the document must be built with json.dumps semantics, "
            "never string substitution: every value must be a "
            "JSON-native type and the round trip must be lossless",
        )

    def test_models_document_port_outside_1_to_65535_raises_argv_error(self):
        piargv = self._piargv()
        for port in (0, -1, 65536):
            with self.subTest(port=port):
                with self.assertRaises(piargv.ArgvError):
                    piargv.models_document(
                        "llamaswap/coder", port, 131072, 16384
                    )

    def test_models_document_port_at_bounds_is_accepted(self):
        piargv = self._piargv()
        for port in (1, 65535):
            with self.subTest(port=port):
                self.assertIsInstance(
                    piargv.models_document(
                        "llamaswap/coder", port, 131072, 16384
                    ),
                    dict,
                )

    def test_models_document_context_window_below_one_raises_argv_error(self):
        piargv = self._piargv()
        for context_window in (0, -1):
            with self.subTest(context_window=context_window):
                with self.assertRaises(piargv.ArgvError):
                    piargv.models_document(
                        "llamaswap/coder", 1234, context_window, 16384
                    )


class TestModelsDocumentHost(PiargvTestCase):
    """Behaviour 1 of ``plans/pi-phase1b-docker.md``: gateway host.

    Pinned signature ``models_document(model_id, port, context_window,
    max_tokens, host="127.0.0.1") -> dict``. The host parameter lets the
    document address llama-swap from inside the Compose network
    (``http://llama-swap:8080/v1``) while omitting it keeps every existing
    caller on ``http://127.0.0.1:<port>/v1`` unchanged.

    The in-network address ``llama-swap`` is the Compose service name on
    ``llm-network`` (``docker-compose.yml`` ports + command rows in the
    plan's interface-facts table), so it is the exact value the
    ``pi-bakeoff`` service will use.
    """

    def test_models_document_default_host_is_loopback(self):
        # Omitting host must keep the exact legacy baseUrl so every
        # existing caller is unchanged - this is the backward-compat pin.
        piargv = self._piargv()
        doc = piargv.models_document("llamaswap/coder", 8080, 131072, 16384)
        self.assertEqual(
            doc["providers"]["llamaswap"]["baseUrl"],
            "http://127.0.0.1:8080/v1",
            "omitting host must yield the legacy loopback baseUrl",
        )

    def test_models_document_explicit_host_is_interpolated_into_base_url(self):
        # Keyword call pins the parameter name; renaming it (e.g. to
        # gateway) fails these tests with a TypeError, which is the
        # point.
        piargv = self._piargv()
        doc = piargv.models_document(
            "llamaswap/coder", 8080, 131072, 16384, host="llama-swap"
        )
        self.assertEqual(
            doc["providers"]["llamaswap"]["baseUrl"],
            "http://llama-swap:8080/v1",
            "the host must be interpolated into the baseUrl, "
            "replacing the loopback default",
        )

    def test_models_document_explicit_host_changes_only_base_url(self):
        # The host parameter must touch exactly one field; every other
        # provider key and the models entry are pinned unchanged.
        piargv = self._piargv()
        doc = piargv.models_document(
            "llamaswap/coder", 8080, 131072, 16384, host="llama-swap"
        )
        self.assertEqual(
            doc,
            {
                "providers": {
                    "llamaswap": {
                        "baseUrl": "http://llama-swap:8080/v1",
                        "api": "openai-completions",
                        "apiKey": "llamaswap-local",
                        "models": [
                            {
                                "id": "llamaswap/coder",
                                "contextWindow": 131072,
                                "maxTokens": 16384,
                            }
                        ],
                    }
                }
            },
            "the host parameter must change only the baseUrl; "
            "api, apiKey and the models list are unchanged",
        )

    def test_models_document_empty_host_raises_argv_error_naming_field(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError) as ctx:
            piargv.models_document(
                "llamaswap/coder", 8080, 131072, 16384, host=""
            )
        self.assertIn(
            "host",
            str(ctx.exception),
            "the error message must name the host field",
        )

    def test_models_document_whitespace_host_raises_argv_error_naming_field(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError) as ctx:
            piargv.models_document(
                "llamaswap/coder", 8080, 131072, 16384, host="   "
            )
        self.assertIn(
            "host",
            str(ctx.exception),
            "the error message must name the host field",
        )

    def test_models_document_host_does_not_disturb_port_validation(self):
        # A valid explicit host must not mask the unchanged port
        # check: out-of-range ports still raise ArgvError.
        piargv = self._piargv()
        for port in (0, 65536):
            with self.subTest(port=port):
                with self.assertRaises(piargv.ArgvError):
                    piargv.models_document(
                        "llamaswap/coder", port, 131072, 16384,
                        host="llama-swap",
                    )


if __name__ == "__main__":
    unittest.main()
