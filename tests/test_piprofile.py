"""Tests for anvilkit.pi.piprofile — the ``~/.anvil/profiles.yaml`` store.

Written before the implementation (TDD, ``plans/pi-phase13-profiles.md``).
This file covers behaviour 1 ("name-charset"), behaviour 2
("token-env-derivation"), behaviour 4 ("save-writes-record") and behaviour 5
("save-updates-in-place"); the later behaviours (``load_profile``,
``list_profiles``, ``resolve_token``) will be added here as separate test
classes as they are implemented.

``piprofile`` is imported inside each test body rather than at collection
time, so the file always collects cleanly while the store behaviours remain
unimplemented: a missing ``save_profile`` surfaces as an ``AttributeError``
naming the function, not as a collection error in this file. ``yamlio`` is
imported at the top because it is already green.
"""

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from anvilkit import yamlio

# The tests own these values; the module must derive its verdict from the
# name's characters, not from a hardcoded allowlist.
ACCEPTED_NAMES = [
    "project-x",
    "api.v2",
    "web_ui",
    "A9",
]

OUT_OF_CHARSET_NAMES = [
    "my project!",
    "my_project?",
]

LEADING_HYPHEN_NAMES = ["-project", "-"]
LEADING_DOT_NAMES = [".hidden", "."]
LEADING_DIGIT_NAMES = ["2cool", "0", "123"]


class ValidNameTestCase(unittest.TestCase):
    """Behaviour 1: name-charset."""

    def _valid_name(self):
        """Import anvilkit.pi.piprofile and return its ``valid_name``.

        Fails with a ModuleNotFoundError naming the missing module while the
        store is unimplemented, and with an AttributeError naming
        ``valid_name`` once the module exists without the function.
        """
        return importlib.import_module("anvilkit.pi.piprofile").valid_name

    def test_valid_name_accepts_charset_names_returns_true(self):
        valid_name = self._valid_name()
        for name in ACCEPTED_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), True)

    def test_valid_name_rejects_out_of_charset_character_returns_false(self):
        valid_name = self._valid_name()
        for name in OUT_OF_CHARSET_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), False)

    def test_valid_name_rejects_empty_string_returns_false(self):
        valid_name = self._valid_name()
        self.assertIs(valid_name(""), False)

    def test_valid_name_rejects_leading_hyphen_returns_false(self):
        valid_name = self._valid_name()
        for name in LEADING_HYPHEN_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), False)

    def test_valid_name_rejects_leading_dot_returns_false(self):
        valid_name = self._valid_name()
        for name in LEADING_DOT_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), False)

    def test_valid_name_rejects_leading_digit_returns_false(self):
        valid_name = self._valid_name()
        for name in LEADING_DIGIT_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), False)


# Behaviour 2: the same names that pass behaviour 1, paired with the exact
# environment variable each must derive to.
EXPECTED_TOKEN_ENV = {
    "project-x": "GITHUB_TOKEN_PROJECT_X",
    "api.v2": "GITHUB_TOKEN_API_V2",
    "web_ui": "GITHUB_TOKEN_WEB_UI",
    "A9": "GITHUB_TOKEN_A9",
}

# One invalid name per way of failing behaviour 1.
INVALID_TOKEN_ENV_NAMES = [
    "",
    "my project!",
    "-project",
    ".hidden",
    "2cool",
]

#: The charset a failure message must quote so the operator can fix the
#: name without reading the source.
ALLOWED_CHARSET = "[A-Za-z0-9._-]"


class TokenEnvDerivationTestCase(unittest.TestCase):
    """Behaviour 2: token-env-derivation."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviour 1), so the import succeeds and a missing
        ``token_env_for`` surfaces as an ``AttributeError`` naming the
        function, not as a collection error.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def test_token_env_for_derives_expected_env_name(self):
        module = self._module()
        for name, expected in EXPECTED_TOKEN_ENV.items():
            with self.subTest(name=name):
                self.assertEqual(module.token_env_for(name), expected)

    def test_token_env_for_deterministic_across_calls(self):
        module = self._module()
        for name in EXPECTED_TOKEN_ENV:
            with self.subTest(name=name):
                self.assertEqual(
                    module.token_env_for(name),
                    module.token_env_for(name),
                )

    def test_token_env_for_invalid_name_raises_profile_error(self):
        module = self._module()
        for name in INVALID_TOKEN_ENV_NAMES:
            with self.subTest(name=name):
                # A raise, not a silently sanitised string, is the contract:
                # assertRaises fails if token_env_for returns anything.
                self.assertRaises(module.ProfileError, module.token_env_for, name)

    def test_token_env_for_error_message_names_name_and_charset(self):
        module = self._module()
        for name in INVALID_TOKEN_ENV_NAMES:
            with self.subTest(name=name):
                with self.assertRaises(module.ProfileError) as ctx:
                    module.token_env_for(name)
                message = str(ctx.exception)
                if name:
                    self.assertIn(name, message)
                self.assertIn(ALLOWED_CHARSET, message)


# Behaviour 4: the record ``save_profile`` must write. The values are owned
# by the tests; ``token_env`` is the exact derivation behaviour 2 already
# pins for ``project-x``.
SAVE_RECORD = {
    "name": "project-x",
    "owner": "octo-org",
    "repo": "project-x",
    "base": "main",
    "token_env": "GITHUB_TOKEN_PROJECT_X",
}

#: Names that fail behaviour 1; one per way of failing it.
INVALID_SAVE_NAMES = ["-project", ".hidden", "2cool"]


class SaveProfileWritesRecordTestCase(unittest.TestCase):
    """Behaviour 4: save-writes-record."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1 and 2 are green), so the import
        succeeds and a missing ``save_profile`` surfaces as an
        ``AttributeError`` naming the function, not as a collection error.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def _save(self, module, root, name, target):
        return module.save_profile(
            root=root,
            name=name,
            path=target,
            owner=SAVE_RECORD["owner"],
            repo=SAVE_RECORD["repo"],
            base=SAVE_RECORD["base"],
            project={},
        )

    def test_save_profile_writes_record_to_profiles_yaml(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project-x"
            target.mkdir()
            root = Path(tmp) / ".anvil"

            self._save(module, root, "project-x", target)

            record = yamlio.load(root / "profiles.yaml")

            # The store is versioned and keyed by the profile name.
            self.assertEqual(record["version"], 1)
            self.assertIn("project-x", record)

            # The profile block carries the resolved record.
            profile = record["project-x"]
            self.assertEqual(
                profile["path"], os.path.abspath(str(target))
            )
            self.assertEqual(profile["owner"], SAVE_RECORD["owner"])
            self.assertEqual(profile["repo"], SAVE_RECORD["repo"])
            self.assertEqual(profile["base"], SAVE_RECORD["base"])

    def test_save_profile_derives_token_env(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project-x"
            target.mkdir()
            root = Path(tmp) / ".anvil"

            self._save(module, root, "project-x", target)

            profile = yamlio.load(root / "profiles.yaml")["project-x"]

            # The known derivation from behaviour 2, re-derived through the
            # module's own function so the test pins the contract, not a copy.
            self.assertEqual(
                profile["token_env"],
                module.token_env_for("project-x"),
            )
            self.assertEqual(profile["token_env"], SAVE_RECORD["token_env"])

    def test_save_profile_keeps_project_block_as_given(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project-x"
            target.mkdir()
            # An empty dict is a valid block; a populated one round-trips.
            for project in ({}, {"name": "project-x", "structure": "flat"}):
                with self.subTest(project=project):
                    root = Path(tmp) / ".anvil"
                    module.save_profile(
                        root=root,
                        name=SAVE_RECORD["name"],
                        path=target,
                        owner=SAVE_RECORD["owner"],
                        repo=SAVE_RECORD["repo"],
                        base=SAVE_RECORD["base"],
                        project=project,
                    )
                    profile = yamlio.load(root / "profiles.yaml")[
                        "project-x"
                    ]
                    self.assertEqual(profile["project"], project)

    def test_save_profile_creates_root_parent_directories(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project-x"
            target.mkdir()
            # Three levels that do not exist yet; the write must create them.
            root = Path(tmp) / "deep" / "nested" / ".anvil"
            self.assertFalse(root.exists())

            self._save(module, root, "project-x", target)

            self.assertTrue((root / "profiles.yaml").is_file())

    def test_save_profile_invalid_name_raises_profile_error(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project-x"
            target.mkdir()
            root = Path(tmp) / ".anvil"

            for name in INVALID_SAVE_NAMES:
                with self.subTest(name=name):
                    with self.assertRaises(module.ProfileError) as ctx:
                        self._save(module, root, name, target)

                    # The offending name is named, not swallowed.
                    if name:
                        self.assertIn(name, str(ctx.exception))
                    # Nothing is written: no store file, no root directory.
                    self.assertFalse((root / "profiles.yaml").exists())

    def test_save_profile_missing_target_path_raises_profile_error(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            root = Path(tmp) / ".anvil"

            with self.assertRaises(module.ProfileError) as ctx:
                self._save(module, root, "project-x", missing)

            # The offending path is named so the operator can fix it.
            self.assertIn(str(missing), str(ctx.exception))
            # Nothing is written.
            self.assertFalse((root / "profiles.yaml").exists())

    def test_save_profile_target_path_is_file_raises_profile_error(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            not_a_dir = Path(tmp) / "a-file"
            not_a_dir.write_text("not a directory\n", encoding="utf-8")
            root = Path(tmp) / ".anvil"

            with self.assertRaises(module.ProfileError) as ctx:
                self._save(module, root, "project-x", not_a_dir)

            self.assertIn(str(not_a_dir), str(ctx.exception))
            self.assertFalse((root / "profiles.yaml").exists())


# Behaviour 5: a store already holding the record, re-saved under the same
# name and path carrying a changed identity field. The values are owned by
# the tests; ``token_env`` is the derivation behaviour 2 pins for
# ``project-x``, and the path is the absolute form behaviour 4 writes.
RECORD_NAME = "project-x"
RECORD_OWNER = "octo-org"
RECORD_REPO = "project-x"
RECORD_BASE = "main"

#: Each identity field, changed to a distinct new value, with the other two
#: fields expected to keep their original values.
CHANGED_FIELD_SCENARIOS = [
    ("owner", "new-owner", RECORD_REPO, RECORD_BASE),
    ("repo", RECORD_OWNER, "renamed-repo", RECORD_BASE),
    ("base", RECORD_OWNER, RECORD_REPO, "develop"),
]


class SaveProfileUpdatesInPlaceTestCase(unittest.TestCase):
    """Behaviour 5: save-updates-in-place."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1, 2 and 4 are green), so the import
        succeeds and a missing ``save_profile`` surfaces as an
        ``AttributeError`` naming the function, not as a collection error.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def _save(self, module, root, target, **overrides):
        kwargs = dict(
            root=root,
            name=RECORD_NAME,
            path=target,
            owner=RECORD_OWNER,
            repo=RECORD_REPO,
            base=RECORD_BASE,
            project={},
        )
        kwargs.update(overrides)
        module.save_profile(**kwargs)

    def test_save_profile_same_name_and_path_changed_field_updates_record_in_place(self):
        module = self._module()
        # A fresh store per scenario, each already holding the record.
        for _, owner, repo, base in CHANGED_FIELD_SCENARIOS:
            with self.subTest(owner=owner, repo=repo, base=base):
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / RECORD_NAME
                    target.mkdir()
                    root = Path(tmp) / ".anvil"

                    # The store already holds the record at the target
                    # directory; provisioning again changes one field.
                    self._save(module, root, target)
                    self._save(
                        module, root, target,
                        owner=owner, repo=repo, base=base,
                    )

                    record = yamlio.load(root / "profiles.yaml")

                    # The store still holds exactly one profile.
                    self.assertEqual(
                        sorted(k for k in record if k != "version"),
                        [RECORD_NAME],
                    )
                    # version: 1 is preserved by the in-place update.
                    self.assertEqual(record["version"], 1)

                    profile = record[RECORD_NAME]
                    self.assertEqual(profile["owner"], owner)
                    self.assertEqual(profile["repo"], repo)
                    self.assertEqual(profile["base"], base)
                    # The path and token_env are unchanged by the update:
                    # same directory, same name.
                    self.assertEqual(
                        profile["path"], os.path.abspath(str(target))
                    )
                    self.assertEqual(
                        profile["token_env"],
                        module.token_env_for(RECORD_NAME),
                    )

    def test_save_profile_provisioning_twice_creates_no_second_record(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / RECORD_NAME
            target.mkdir()
            root = Path(tmp) / ".anvil"

            # Provisioning twice is the normal path, not an exception.
            self._save(module, root, target)
            self._save(module, root, target)

            record = yamlio.load(root / "profiles.yaml")
            self.assertEqual(
                sorted(k for k in record if k != "version"),
                [RECORD_NAME],
            )
            self.assertEqual(record["version"], 1)
            profile = record[RECORD_NAME]
            self.assertEqual(profile["path"], os.path.abspath(str(target)))
            self.assertEqual(profile["owner"], RECORD_OWNER)
            self.assertEqual(profile["repo"], RECORD_REPO)
            self.assertEqual(profile["base"], RECORD_BASE)
            self.assertEqual(
                profile["token_env"], module.token_env_for(RECORD_NAME)
            )


# Behaviour 6: a store holding ``old-name`` at a real directory, re-saved
# under ``new-name`` for that SAME path. The record must be renamed in
# place — one path, one profile — carrying its ``project`` block across,
# with ``token_env`` re-derived from the new name. The values are owned by
# the tests; the re-save supplies its own owner/repo/base so the record's
# identity fields are proven to come from the re-save, not the old record.
RENAME_OLD_NAME = "old-name"
RENAME_NEW_NAME = "new-name"

#: The populated project block the first save writes and the rename must
#: carry across untouched.
RENAME_PROJECT_BLOCK = {
    "name": "project-x",
    "structure": "anvilkit/   python package\nplans/    decision record\n",
    "configuration": "gateway port 8080\ncontext 32k",
}

#: Identity supplied on the re-save; distinct from the first save so the
#: assertions cannot be satisfied by the old record's values.
RENAME_OLD_IDENTITY = ("octo-org", "project-x", "main")
RENAME_NEW_IDENTITY = ("new-org", "renamed-repo", "develop")


class SaveProfileRenamesOnSamePathTestCase(unittest.TestCase):
    """Behaviour 6: save-renames-on-same-path."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1, 2, 4 and 5 are green), so the
        import succeeds and the assertions below surface as genuine
        failures against the store contents, not as an AttributeError.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def test_save_profile_same_path_new_name_renames_record_in_place(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project-x"
            target.mkdir()
            root = Path(tmp) / ".anvil"

            # The store holds old-name at the real directory, with a
            # populated project block.
            module.save_profile(
                root=root,
                name=RENAME_OLD_NAME,
                path=target,
                owner=RENAME_OLD_IDENTITY[0],
                repo=RENAME_OLD_IDENTITY[1],
                base=RENAME_OLD_IDENTITY[2],
                project=RENAME_PROJECT_BLOCK,
            )
            # Re-saved under the SAME path but the NEW name.
            module.save_profile(
                root=root,
                name=RENAME_NEW_NAME,
                path=target,
                owner=RENAME_NEW_IDENTITY[0],
                repo=RENAME_NEW_IDENTITY[1],
                base=RENAME_NEW_IDENTITY[2],
                project=RENAME_PROJECT_BLOCK,
            )

            record = yamlio.load(root / "profiles.yaml")

            # One path, one profile: the store holds exactly one profile,
            # under new-name, and old-name is gone.
            self.assertEqual(
                sorted(k for k in record if k != "version"),
                [RENAME_NEW_NAME],
            )
            self.assertNotIn(RENAME_OLD_NAME, record)

            profile = record[RENAME_NEW_NAME]

            # The path is unchanged (absolute) by the rename.
            self.assertEqual(
                profile["path"], os.path.abspath(str(target))
            )
            # The project block carried across from the old record.
            self.assertEqual(profile["project"], RENAME_PROJECT_BLOCK)
            # token_env re-derived from the NEW name, through the module's
            # own function so the test pins the contract, not a copy.
            self.assertEqual(
                profile["token_env"],
                module.token_env_for(RENAME_NEW_NAME),
            )
            self.assertEqual(profile["token_env"], "GITHUB_TOKEN_NEW_NAME")
            # owner/repo/base are as supplied on the re-save, not the
            # old record's.
            self.assertEqual(profile["owner"], RENAME_NEW_IDENTITY[0])
            self.assertEqual(profile["repo"], RENAME_NEW_IDENTITY[1])
            self.assertEqual(profile["base"], RENAME_NEW_IDENTITY[2])
            # version: 1 is preserved by the rename.
            self.assertEqual(record["version"], 1)
