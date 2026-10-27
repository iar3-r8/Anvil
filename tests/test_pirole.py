"""Boundary pins for ``plans/pi-phase6-single-role.md`` behaviours 1-3.

These are the loop's home test module (``tests/test_pirole.py``). The batch
covers the three boundary pins that assert *today's* ``pisandbox`` / runner
contract before ``pirole`` / ``pidriver`` build on top of it, so nothing the
later behaviours add can quietly invalidate the seam:

1. ``sandbox-run-argv-unchanged`` - the run argv ends at the image tag and
   carries no ``pi`` token; the append point the driver relies on.
2. ``sandbox-refuses-credential-env`` - a credential-looking env name is
   refused with the credential reason, nothing is returned.
3. ``runner-seam-contract`` - ``subprocess_runner`` invoked with the
   invocation-dict contract returns exactly the six result keys with their
   documented types.

These pin existing, already-landed code (``anvilkit/pi/pisandbox.py`` and
``anvilkit/pi/pibakeoff.py``). A pin that cannot be red against the current
contract is still worth recording: it is the boundary the later behaviours
must not move. They are written against the documented public contract only -
no source text, no production change.

Documented runner contract, cited from
``anvilkit/pi/pibakeoff.py`` ``subprocess_runner`` (and mirrored in
``anvilkit/pi/piapproval.py``): one invocation dict in
(``argv`` list[str], ``cwd`` str, ``stdin`` str, ``timeout_s`` float, optional
``env`` dict) and exactly six result keys out -
``exit_code`` (int), ``stdout`` (str), ``stderr`` (str),
``wall_time_s`` (float), ``timed_out`` (bool), ``evidence`` (str).

Behaviour 4 (``role-table-resolves-four-roles``) and behaviour 5
(``role-argv-is-list-and-complete``) are also tested here:
``pirole.resolve(name, coder_model_id, frontier_model_id)`` maps each of the
four role names to a definition dict carrying its ``model_id``, ``tier``,
``prompt_path`` and ``tools`` - the architect is the only frontier-tier role
(frontier model id), while coder, tester and docs run on the local coder
model - and an unknown name raises ``RoleError`` naming it and listing the
four known roles. Behaviour 5 pins ``role_argv(definition, session_id,
task)``: a ``List[str]`` (never a ``str``) carrying ``pi``, ``--mode json``,
the model, the prompt path, the full tool list, the session id, ``--no-mcp``,
``-a``, the ``--`` terminator, and the task last after it - and an empty
model id, prompt path or task raises ``RoleError`` naming the field. The
``pirole`` import is deferred into the tests so that, while a part of the
module does not yet exist, those tests fail at the import or attribute step
rather than breaking collection of the boundary pins.
"""

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pibakeoff as pibakeoff
from anvilkit.pi import pisandbox as pisandbox

# Pinned inputs for the run-argv pin. The tag is the phase-6 sandbox tag;
# the env map is the full three-name allowlist the sandbox permits.
REPO_PATH = "/home/u/project"
TAG = "pi-sandbox"
ALLOWED_ENV = {
    "PI_GATEWAY_HOST": "llama-swap",
    "PI_GATEWAY_PORT": "8080",
    "PI_CODING_AGENT_DIR": "/home/sandbox/.pi/agent",
}

# The six runner-contract keys, pinned exactly: no more, no less.
RUNNER_RESULT_KEYS = {
    "exit_code",
    "stdout",
    "stderr",
    "wall_time_s",
    "timed_out",
    "evidence",
}


class PiRoleBoundaryPinTestCase(unittest.TestCase):
    """Shared per-test temp directory for the runner-seam pin."""

    def _tmpdir(self) -> Path:
        """A per-test temporary directory, cleaned up automatically."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)


class TestSandboxRunArgvUnchanged(PiRoleBoundaryPinTestCase):
    """Behaviour 1: the run argv ends at the tag and carries no ``pi`` token.

    Pins the append point the phase-6 driver relies on: ``run_argv`` builds
    the container command and stops at the image tag, so the driver can
    append the role argv immediately after it.
    """

    def test_run_argv_with_three_name_env_ends_at_tag_and_has_no_pi_token(self):
        # Arrange: a repo path, the sandbox tag, the full three-name env map.
        # Act.
        argv = pisandbox.run_argv(REPO_PATH, TAG, env=dict(ALLOWED_ENV))
        # Assert: a list of str tokens, the last token is the tag, and no
        # ``pi`` token appears anywhere in the vector.
        self.assertIsInstance(argv, list)
        for token in argv:
            self.assertIsInstance(token, str)
        self.assertEqual(
            TAG,
            argv[-1],
            "the run argv must end at the image tag so the driver can append "
            "the role argv after it; got tail: %r" % argv[-3:],
        )
        self.assertNotIn(
            "pi",
            argv,
            "no ``pi`` token may appear in the run argv; the pi invocation "
            "is the driver's job, not part of this argv; got: %r" % (argv,),
        )


class TestSandboxRefusesCredentialEnv(PiRoleBoundaryPinTestCase):
    """Behaviour 2: a credential-looking env name is refused, nothing returned.

    ``ANTHROPIC_API_KEY`` matches the ``KEY`` credential marker and must be
    refused with the credential reason before it can reach the container,
    where every process can read any variable passed in.
    """

    def test_run_argv_credential_env_is_refused_with_sandbox_error(self):
        # Arrange: an env map carrying a credential-looking name.
        credential_env = {"ANTHROPIC_API_KEY": "x"}
        # Act / Assert: nothing is returned; a SandboxError is raised that
        # names the credential reason and the offending env name.
        with self.assertRaises(pisandbox.SandboxError) as ctx:
            pisandbox.run_argv(REPO_PATH, TAG, env=credential_env)
        message = str(ctx.exception)
        self.assertIn(
            "ANTHROPIC_API_KEY",
            message,
            "the refusal must name the offending env name; got: %r" % message,
        )
        self.assertTrue(
            "credential" in message.lower(),
            "the refusal must state the credential reason (values passed in "
            "are readable by every process inside); got: %r" % message,
        )


class TestRunnerSeamContract(PiRoleBoundaryPinTestCase):
    """Behaviour 3: ``subprocess_runner`` honours the invocation-dict contract.

    A trivial argv (the repo's own interpreter printing a known line) is
    invoked with the documented invocation dict; the result must be exactly
    the six runner-contract keys with their documented types, and on this
    trivial success the documented success-path values hold.
    """

    def test_subprocess_runner_trivial_argv_returns_six_keys_with_documented_types(self):
        # Arrange: a trivial argv via sys.executable, and the documented
        # invocation dict.
        cwd = self._tmpdir()
        argv = [sys.executable, "-c", "print('ok')"]
        spec = {
            "argv": argv,
            "cwd": str(cwd),
            "stdin": "/dev/null",
            "timeout_s": 10.0,
        }
        # Act.
        result = pibakeoff.subprocess_runner(spec)
        # Assert: exactly the six runner-contract keys, no more, no less.
        self.assertIsInstance(result, dict)
        self.assertEqual(
            RUNNER_RESULT_KEYS,
            set(result),
            "the runner must return exactly the six runner-contract keys, "
            "no more, no less; got: %r" % (sorted(result),),
        )
        # Each key carries its documented type.
        self.assertIsInstance(result["exit_code"], int)
        self.assertNotIsInstance(result["exit_code"], bool)
        self.assertIsInstance(result["stdout"], str)
        self.assertIsInstance(result["stderr"], str)
        self.assertIsInstance(result["wall_time_s"], float)
        self.assertIs(type(result["timed_out"]), bool)
        self.assertIsInstance(result["evidence"], str)
        # The documented success path for this trivial, non-blocked run.
        self.assertEqual(
            0,
            result["exit_code"],
            "a trivial successful child must report exit code 0; got: %r"
            % result["exit_code"],
        )
        self.assertIs(
            result["timed_out"],
            False,
            "a run that completes inside the budget is not timed out; got: %r"
            % result["timed_out"],
        )
        self.assertEqual(
            "",
            result["evidence"],
            "evidence is empty unless the run was blocked; got: %r"
            % result["evidence"],
        )
        self.assertEqual(
            "ok\n",
            result["stdout"],
            "the runner must capture the child's stdout verbatim; got: %r"
            % result["stdout"],
        )
        self.assertGreaterEqual(result["wall_time_s"], 0.0)


# Behaviour 4: role-table-resolves-four-roles. The four role names and their
# tiering come from the plan (architect is frontier-tier, the other three are
# local-tier); the definition shape is the dict ``resolve`` returns, pinned
# on the four keys the role table must carry.
ROLES = ("architect", "coder", "tester", "docs")
CODER_MODEL_ID = "llama-swapped-coder-72b"
FRONTIER_MODEL_ID = "claude-sonnet-4-5"


class RoleResolveTestCase(PiRoleBoundaryPinTestCase):
    """Shared deferred import of the not-yet-existing ``pirole`` module.

    The import happens inside each test, not at module top level, so that
    while ``anvilkit/pi/pirole.py`` does not yet exist the tests fail at
    the import step (ModuleNotFoundError) instead of breaking collection
    of the boundary pins above.
    """

    def _import_pirole(self):
        from anvilkit.pi import pirole as pirole

        return pirole


class TestResolveRoles(RoleResolveTestCase):
    """Each of the four role names resolves to its definition dict."""

    def test_resolve_architect_carries_frontier_model_tier_and_paths(self):
        # Arrange: the frontier-tier role name and both model ids.
        pirole = self._import_pirole()
        # Act.
        definition = pirole.resolve(
            "architect", CODER_MODEL_ID, FRONTIER_MODEL_ID
        )
        # Assert: the architect is the only frontier-tier role and carries
        # the frontier model id, its own prompt path and the default tools.
        self.assertEqual(FRONTIER_MODEL_ID, definition["model_id"])
        self.assertEqual("frontier", definition["tier"])
        self.assertEqual(".pi/roles/architect.md", definition["prompt_path"])
        self.assertEqual("read,bash,edit,write", definition["tools"])

    def test_resolve_coder_carries_local_model_tier_and_paths(self):
        # Arrange: a local-tier role name and both model ids.
        pirole = self._import_pirole()
        # Act.
        definition = pirole.resolve(
            "coder", CODER_MODEL_ID, FRONTIER_MODEL_ID
        )
        # Assert: the coder runs on the local model, not the frontier one.
        self.assertEqual(CODER_MODEL_ID, definition["model_id"])
        self.assertEqual("local", definition["tier"])
        self.assertEqual(".pi/roles/coder.md", definition["prompt_path"])
        self.assertEqual("read,bash,edit,write", definition["tools"])

    def test_resolve_tester_carries_local_model_tier_and_paths(self):
        # Arrange: a local-tier role name and both model ids.
        pirole = self._import_pirole()
        # Act.
        definition = pirole.resolve(
            "tester", CODER_MODEL_ID, FRONTIER_MODEL_ID
        )
        # Assert: the tester runs on the local model with its own prompt.
        self.assertEqual(CODER_MODEL_ID, definition["model_id"])
        self.assertEqual("local", definition["tier"])
        self.assertEqual(".pi/roles/tester.md", definition["prompt_path"])
        self.assertEqual("read,bash,edit,write", definition["tools"])

    def test_resolve_docs_carries_local_model_tier_and_paths(self):
        # Arrange: a local-tier role name and both model ids.
        pirole = self._import_pirole()
        # Act.
        definition = pirole.resolve(
            "docs", CODER_MODEL_ID, FRONTIER_MODEL_ID
        )
        # Assert: the docs role runs on the local model with its own prompt.
        self.assertEqual(CODER_MODEL_ID, definition["model_id"])
        self.assertEqual("local", definition["tier"])
        self.assertEqual(".pi/roles/docs.md", definition["prompt_path"])
        self.assertEqual("read,bash,edit,write", definition["tools"])


class TestResolveUnknownRole(RoleResolveTestCase):
    """An unknown name raises RoleError naming the name and the four roles."""

    def test_resolve_unknown_name_raises_role_error_naming_it_and_known_roles(self):
        # Arrange: a name that is not one of the four roles.
        pirole = self._import_pirole()
        # Act / Assert: a RoleError is raised that names the unknown name
        # and lists all four known roles, so the caller can see what exists.
        with self.assertRaises(pirole.RoleError) as ctx:
            pirole.resolve("manager", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        message = str(ctx.exception)
        self.assertIn(
            "manager",
            message,
            "the error must name the unknown role; got: %r" % message,
        )
        for role in ROLES:
            self.assertIn(
                role,
                message,
                "the error must list the known role %r among the four "
                "roles; got: %r" % (role, message),
            )


# The argv builder takes a resolved definition, a session id and a task and
# returns the pi invocation as a list of tokens. The session id used here is
# a valid one (letters, digits, dots, underscores and dashes, starting and
# ending with a letter or digit) so the happy path is pinned on the token
# vector alone.
SESSION_ID = "20261027T140530Z-coder"
TASK = "add the role argv builder"


class TestRoleArgvCompleteVector(RoleResolveTestCase):
    """The role argv is a list of str tokens, complete and in order.

    The token vector is pinned end to end: the pi executable first, the JSON
    mode, the model, the prompt path, the full tool list, the session id, the
    MCP kill switch, the project-approval flag, the option terminator, and
    finally the task after it.
    """

    def test_role_argv_coder_session_task_is_list_of_str_with_complete_vector(self):
        # Arrange: a resolved coder definition, a valid session id and a task.
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        # Act.
        argv = pirole.role_argv(definition, SESSION_ID, TASK)
        # Assert: a list (never a str) whose tokens are all str.
        self.assertIsInstance(
            argv,
            list,
            "the role argv must be a list of tokens, never a string; got: %r"
            % type(argv).__name__,
        )
        for token in argv:
            self.assertIsInstance(token, str)
        # The complete token vector, in order, with the task last after the
        # option terminator.
        self.assertEqual(
            [
                "pi",
                "--mode",
                "json",
                "--model",
                CODER_MODEL_ID,
                "--append-system-prompt",
                ".pi/roles/coder.md",
                "--tools",
                "read,bash,edit,write",
                "--session-id",
                SESSION_ID,
                "--no-mcp",
                "-a",
                "--",
                TASK,
            ],
            argv,
            "the role argv must carry exactly these tokens in this order, "
            "the task last after the terminator; got: %r" % (argv,),
        )
        # The task is the final token, positioned after the "--" terminator.
        self.assertEqual(
            "--",
            argv[-2],
            "the option terminator must sit immediately before the task; "
            "got: %r" % (argv[-3:],),
        )


class TestRoleArgvEmptyFieldRaises(RoleResolveTestCase):
    """An empty model id, prompt path or task raises RoleError naming it.

    The definition is built by ``resolve`` and then one field is blanked, so
    each failure is pinned on exactly one missing value while the other
    inputs stay valid.
    """

    def test_role_argv_empty_model_id_raises_role_error_naming_the_field(self):
        # Arrange: a resolved coder definition whose model id is blanked.
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        definition["model_id"] = ""
        # Act / Assert: nothing is returned; a RoleError names the field.
        with self.assertRaises(pirole.RoleError) as ctx:
            pirole.role_argv(definition, SESSION_ID, TASK)
        message = str(ctx.exception)
        self.assertIn(
            "model_id",
            message,
            "the error must name the empty model id field; got: %r" % message,
        )

    def test_role_argv_empty_prompt_path_raises_role_error_naming_the_field(self):
        # Arrange: a resolved coder definition whose prompt path is blanked.
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        definition["prompt_path"] = ""
        # Act / Assert: nothing is returned; a RoleError names the field.
        with self.assertRaises(pirole.RoleError) as ctx:
            pirole.role_argv(definition, SESSION_ID, TASK)
        message = str(ctx.exception)
        self.assertIn(
            "prompt_path",
            message,
            "the error must name the empty prompt path field; got: %r"
            % message,
        )

    def test_role_argv_empty_task_raises_role_error_naming_the_field(self):
        # Arrange: a valid definition and session id, an empty task.
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        # Act / Assert: nothing is returned; a RoleError names the field.
        with self.assertRaises(pirole.RoleError) as ctx:
            pirole.role_argv(definition, SESSION_ID, "")
        message = str(ctx.exception)
        self.assertIn(
            "task",
            message,
            "the error must name the empty task field; got: %r" % message,
        )


# The hostile task pins the verbatim-pass-through guarantee: it opens with a
# dash (which a naive option parser would treat as a flag) and carries every
# shell metacharacter the plan names - a semicolon, a command substitution, a
# backtick and a double quote.
HOSTILE_TASK = '-fix; echo $(id) `id` "quoted"'


class TestRoleArgvHostileTaskVerbatim(RoleResolveTestCase):
    """A hostile task crosses into the argv unaltered, after the terminator.

    The builder returns a list, never a shell string: the task is exactly one
    element, byte-identical to the input, positioned immediately after the
    ``--`` option terminator. No shell token is produced and no quoting is
    applied - the list goes to ``subprocess`` with no shell, so the
    metacharacters that would be live in a shell line are inert data here.
    """

    def test_role_argv_hostile_task_is_a_single_byte_identical_element(self):
        # Arrange: a resolved coder definition, a valid session id and a task
        # whose text opens with a dash and carries ;, $(id), a backtick and a
        # quote.
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        # Act.
        argv = pirole.role_argv(definition, SESSION_ID, HOSTILE_TASK)
        # Assert: the task is exactly one element and byte-identical to the
        # input, so nothing was split, sanitized or wrapped on the way in.
        self.assertIsInstance(
            argv,
            list,
            "the role argv must be a list of tokens, never a shell string; "
            "got: %r" % type(argv).__name__,
        )
        matches = [token for token in argv if token == HOSTILE_TASK]
        self.assertEqual(
            1,
            len(matches),
            "the hostile task must be exactly one argv element, byte-identical "
            "to the input; got %d element(s) equal to the task in: %r"
            % (len(matches), argv),
        )

    def test_role_argv_hostile_task_sits_immediately_after_the_option_terminator(self):
        # Arrange: the same resolved definition and hostile task.
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        # Act.
        argv = pirole.role_argv(definition, SESSION_ID, HOSTILE_TASK)
        # Assert: the task is positioned immediately after the ``--``
        # terminator, so the leading dash is data, not an option.
        self.assertIn(
            "--",
            argv,
            "the option terminator must be present in the role argv; got: %r"
            % (argv,),
        )
        terminator = argv.index("--")
        self.assertEqual(
            HOSTILE_TASK,
            argv[terminator + 1],
            "the hostile task must sit immediately after the -- terminator, "
            "so a leading dash is data, not an option; got: %r" % (argv,),
        )
        self.assertEqual(
            len(argv) - 1,
            terminator + 1,
            "the hostile task must be the final token, after the -- "
            "terminator; got: %r" % (argv,),
        )

    def test_role_argv_hostile_task_is_never_quoted_escaped_or_split(self):
        # Arrange: the same resolved definition and hostile task.
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        # Act.
        argv = pirole.role_argv(definition, SESSION_ID, HOSTILE_TASK)
        # Assert: no quoting is applied - no token wraps the task in single
        # or double quotes, and no token carries an escaped form of it.
        self.assertNotIn(
            "'{}'".format(HOSTILE_TASK),
            argv,
            "no quoting may be applied to the task, the list goes to "
            "subprocess with no shell; got: %r" % (argv,),
        )
        self.assertNotIn(
            '"{}"'.format(HOSTILE_TASK),
            argv,
            "no quoting may be applied to the task, the list goes to "
            "subprocess with no shell; got: %r" % (argv,),
        )
        self.assertNotIn(
            HOSTILE_TASK.replace('"', '\\"'),
            argv,
            "no escaping may be applied to the task, the list goes to "
            "subprocess with no shell; got: %r" % (argv,),
        )
        # Assert: no shell token is produced - no token other than the task
        # is a fragment of it, which would mean the task was split into
        # shell words.
        fragments = [
            token for token in argv if token != HOSTILE_TASK and token in HOSTILE_TASK
        ]
        self.assertEqual(
            [],
            fragments,
            "no shell token may be produced from the task; every token other "
            "than the task itself must be a fixed flag or value; got: %r"
            % (fragments,),
        )


# Pi's rule for session ids (doc/external/pi-dev/cli.md, Sessions
# constraints): ids accept letters, numbers, ".", "_" and "-", and must start
# and end with a letter or number. Each invalid id below violates exactly one
# part of the rule and must be refused, never silently repaired.
INVALID_SESSION_IDS = ("-leading", "trailing-", "has space", "has/slash", "")


class TestRoleArgvSessionIdValidated(RoleResolveTestCase):
    """Pi's session-id rule is enforced on the role_argv input.

    A valid id crosses into the argv byte-identical, immediately after the
    ``--session-id`` flag; an invalid id is refused with a ``RoleError`` that
    quotes the id and states Pi's rule, so nothing is repaired or rewritten
    on the way through.
    """

    def test_role_argv_valid_session_id_is_accepted_verbatim_after_the_flag(self):
        # Arrange: a resolved coder definition and a valid session id.
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        # Act.
        argv = pirole.role_argv(definition, SESSION_ID, TASK)
        # Assert: the id is one token, byte-identical to the input, sitting
        # immediately after the --session-id flag.
        flag = argv.index("--session-id")
        self.assertEqual(
            SESSION_ID,
            argv[flag + 1],
            "the valid session id must appear verbatim after --session-id; "
            "got: %r" % (argv[flag:flag + 2],),
        )

    def test_role_argv_invalid_session_id_raises_role_error_quoting_id_and_rule(self):
        # Arrange: a resolved coder definition; each invalid id violates one
        # part of Pi's rule (leading dash, trailing dash, space, slash, empty).
        pirole = self._import_pirole()
        definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
        for bad_id in INVALID_SESSION_IDS:
            with self.subTest(session_id=bad_id):
                # Act / Assert: a RoleError is raised - the id is refused,
                # never silently repaired into a valid one, so nothing is
                # returned.
                with self.assertRaises(pirole.RoleError) as ctx:
                    pirole.role_argv(definition, bad_id, TASK)
                message = str(ctx.exception)
                if bad_id:
                    self.assertIn(
                        "'{}'".format(bad_id),
                        message,
                        "the error must quote the offending session id %r; "
                        "got: %r" % (bad_id, message),
                    )
                self.assertIn(
                    "session_id",
                    message,
                    "the error must name the session_id field; got: %r" % message,
                )
                self.assertIn(
                    "letters",
                    message,
                    "the error must state Pi's rule for allowed characters; "
                    "got: %r" % message,
                )
                self.assertIn(
                    "numbers",
                    message,
                    "the error must state Pi's rule for allowed characters; "
                    "got: %r" % message,
                )
                self.assertIn(
                    "start",
                    message,
                    "the error must state Pi's start-of-id rule; got: %r"
                    % message,
                )
                self.assertIn(
                    "end",
                    message,
                    "the error must state Pi's end-of-id rule; got: %r" % message,
                )


# Pi rejects these six session flags alongside --session-id
# (doc/external/pi-dev/cli.md, Sessions constraints): the role argv must
# therefore never emit one, since a role invocation is always --session-id.
CONFLICTING_SESSION_FLAGS = (
   "--session",
   "--continue",
   "-c",
   "--resume",
   "-r",
   "--no-session",
)


class TestRoleArgvOmitsConflictingSessionFlags(RoleResolveTestCase):
   """No role argv carries a flag that conflicts with --session-id.

   Pi rejects --session, --continue, -c, --resume, -r and --no-session
   alongside --session-id (doc/external/pi-dev/cli.md, Sessions
   constraints), so the builder can never emit one. This pins that absence
   on the token vector for every role and for a hostile task. The anti-
   vacuity guard is that each inspected argv is asserted to still carry the
   legitimate --session-id flag, so the absence assertions run against a
   real, complete vector rather than an empty one.
   """

   def test_role_argv_for_all_roles_omits_the_conflicting_session_flags(self):
       # Arrange: every role's resolved definition, a valid session id and
       # the standard task.
       pirole = self._import_pirole()
       for role in ROLES:
           with self.subTest(role=role):
               definition = pirole.resolve(role, CODER_MODEL_ID, FRONTIER_MODEL_ID)
               # Act.
               argv = pirole.role_argv(definition, SESSION_ID, TASK)
               # Assert: the vector is a real, complete one carrying the
               # legitimate --session-id flag, and none of the six
               # conflicting flags appears anywhere in it.
               self.assertIn(
                   "--session-id",
                   argv,
                   "the role argv must carry the legitimate --session-id "
                   "flag; got: %r" % (argv,),
               )
               for flag in CONFLICTING_SESSION_FLAGS:
                   self.assertNotIn(
                       flag,
                       argv,
                       "the role argv must never emit %r, Pi rejects it "
                       "alongside --session-id; got: %r" % (flag, argv),
                   )

   def test_role_argv_with_hostile_task_omits_the_conflicting_session_flags(self):
       # Arrange: a resolved coder definition, a valid session id and the
       # hostile task (dash-leading, carrying shell metacharacters), so the
       # absence check holds for an adversarial final token as well.
       pirole = self._import_pirole()
       definition = pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)
       # Act.
       argv = pirole.role_argv(definition, SESSION_ID, HOSTILE_TASK)
       # Assert: same as above, but the inspected vector ends in the hostile
       # task, proving the check scans the whole token list.
       self.assertIn(
           "--session-id",
           argv,
           "the role argv must carry the legitimate --session-id flag; "
           "got: %r" % (argv,),
       )
       for flag in CONFLICTING_SESSION_FLAGS:
           self.assertNotIn(
               flag,
               argv,
               "the role argv must never emit %r, Pi rejects it alongside "
               "--session-id; got: %r" % (flag, argv),
           )
       # The inspected vector is the complete one, hostile task last after
       # the terminator - not a truncated or empty vector.
       self.assertEqual(HOSTILE_TASK, argv[-1])


# Behaviour 14: decision-seam-holds. A drift guard on the decide/act split:
# ``pirole`` decides (resolves the role, builds the argv) and must never act
# (no subprocess, no docker), so the whole module stays importable and
# exercisable with no container. The scan is done with ``ast`` over the
# module's import nodes, so the guard is about what the module *imports*, not
# about how its source is formatted, and it keeps pinning the seam without
# any production change.


def _imported_module_names(source: str) -> List[str]:
    """The module names a source file imports, via ``ast``.

    ``import subprocess`` yields ``"subprocess"``;
    ``import anvilkit.pi.pisandbox`` yields
    ``"anvilkit.pi.pisandbox"``;
    ``from anvilkit.pi import pisandbox`` yields
    ``"anvilkit.pi.pisandbox"`` (the qualified name) as well as the package
    prefix ``"anvilkit.pi"``. Only real import nodes are read, so string
    content, comments and docstrings can never trip the guard.
    """
    module_names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                module_names.append(node.module)
                for alias in node.names:
                    module_names.append(node.module + "." + alias.name)
    return module_names


class TestDecisionSeamHolds(RoleResolveTestCase):
    """``pirole`` imports nothing that executes: the decide/act split holds.

    The guard has two anti-vacuity controls: a banned set rebuilt from the
    package itself (so a module that later learns to execute a process is
    banned without touching this test), and positive controls run against
    two real, already-landed modules - ``pibakeoff`` really imports
    ``subprocess`` and ``pidriver`` really imports ``anvilkit.pi.pisandbox`` -
    so the scan is proven to flag both halves of the seam before it is
    asserted clean on ``pirole``.
    """

    def _banned_module_prefixes(self) -> List[str]:
        """Rebuild the banned set: the process side and the docker side.

        The process side is every ``anvilkit.pi`` module whose source imports
        ``subprocess`` (the act of executing a command), rebuilt from the
        package so a module that later learns to execute a process is banned
        without touching this test. The docker side is pinned by name:
        ``anvilkit.pi.pisandbox`` builds the docker run argv (the docker side
        of the seam, per the plan's reuse check) without itself importing
        ``subprocess``, so no scan can derive it - it is named here.
        """
        pi_package = REPO_ROOT / "anvilkit" / "pi"
        process_side = set()
        for path in sorted(pi_package.glob("*.py")):
            if path.name == "__init__.py":
                continue
            if "subprocess" in _imported_module_names(path.read_text()):
                process_side.add("anvilkit.pi." + path.stem)
        return sorted({"subprocess", "anvilkit.pi.pisandbox"} | process_side)

    def test_pirole_imports_never_reach_the_process_side_or_the_docker_side(self):
        # Arrange: the module under guard and the banned set rebuilt from the
        # package.
        pirole = self._import_pirole()
        banned = self._banned_module_prefixes()
        # Anti-vacuity control: the scan must flag both real offenders before
        # it is asserted clean, or the guard would pass on an empty pattern.
        pibakeoff_source = (REPO_ROOT / "anvilkit" / "pi" / "pibakeoff.py").read_text()
        self.assertIn(
            "subprocess",
            _imported_module_names(pibakeoff_source),
            "the positive control failed: pibakeoff really imports "
            "subprocess, so the scan must flag it; the guard would be "
            "vacuous",
        )
        pidriver_source = (REPO_ROOT / "anvilkit" / "pi" / "pidriver.py").read_text()
        pidriver_imports = _imported_module_names(pidriver_source)
        self.assertTrue(
            any(
                name.startswith("anvilkit.pi.pisandbox")
                for name in pidriver_imports
            ),
            "the positive control failed: pidriver really imports "
            "anvilkit.pi.pisandbox (the docker-invoking module), so the "
            "scan must flag it; the guard would be vacuous",
        )
        self.assertIn("anvilkit.pi.pisandbox", banned)
        # Act / Assert: the banned names are absent from pirole's imports,
        # including any alias or dotted prefix (e.g.
        # ``from anvilkit.pi import pisandbox``).
        source = Path(pirole.__file__).read_text()
        imported = _imported_module_names(source)
        for name in imported:
            self.assertFalse(
                any(
                    name == banned_name or name.startswith(banned_name + ".")
                    for banned_name in banned
                ),
                "pirole must stay a decision module: it must not import "
                "subprocess or a docker-invoking module (the act belongs to "
                "the driver); found %r in its imports: %r"
                % (name, imported),
            )

    def test_pirole_is_importable_and_exercisable_in_a_fresh_interpreter_with_no_subprocess(self):
        # Arrange: a fresh interpreter that imports pirole and nothing else -
        # no container, and no other anvilkit module that could load
        # subprocess first. The child asserts the seam itself (subprocess
        # never entered sys.modules from that import) and then exercises the
        # whole public surface.
        child = (
            "import json, sys\n"
            "import anvilkit.pi.pirole as pirole\n"
            "params = json.loads(r'''{p}''')\n"
            "if 'subprocess' in sys.modules:\n"
            "    print('SUBPROCESS_LOADED')\n"
            "    sys.exit(3)\n"
            "for role in params['roles']:\n"
            "    definition = pirole.resolve(role, params['coder'], params['frontier'])\n"
            "    argv = pirole.role_argv(definition, params['session_id'], params['task'])\n"
            "    assert argv[0] == 'pi' and argv[-1] == params['task'], argv\n"
            "try:\n"
            "    pirole.resolve('manager', params['coder'], params['frontier'])\n"
            "except pirole.RoleError:\n"
            "    pass\n"
            "else:\n"
            "    print('NO_ROLE_ERROR')\n"
            "    sys.exit(4)\n"
            "print('OK')\n"
        ).format(
            p=json.dumps(
                {
                    "roles": list(ROLES),
                    "coder": CODER_MODEL_ID,
                    "frontier": FRONTIER_MODEL_ID,
                    "session_id": SESSION_ID,
                    "task": TASK,
                }
            )
        )
        spec = {
            "argv": [sys.executable, "-c", child],
            "cwd": str(REPO_ROOT),
            "stdin": "/dev/null",
            "timeout_s": 30.0,
        }
        # Act.
        result = pibakeoff.subprocess_runner(spec)
        # Assert: the fresh interpreter completed, subprocess never loaded
        # from the pirole import, and the whole public surface ran.
        self.assertEqual(
            0,
            result["exit_code"],
            "the fresh interpreter must complete; got exit code %r, stdout "
            "%r, stderr %r"
            % (result["exit_code"], result["stdout"], result["stderr"]),
        )
        self.assertNotIn(
            "SUBPROCESS_LOADED",
            result["stdout"],
            "importing pirole must not load the subprocess module; the "
            "module decides and does not act",
        )
        self.assertNotIn(
            "NO_ROLE_ERROR",
            result["stdout"],
            "an unknown role must still be refused by RoleError",
        )
        self.assertEqual("OK\n", result["stdout"])


if __name__ == "__main__":
    unittest.main()
