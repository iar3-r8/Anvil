"""Tests for anvilkit.pi.piprofile — the ``~/.anvil/profiles.yaml`` store.

Written before the implementation (TDD, ``plans/pi-phase13-profiles.md``).
This file covers behaviour 1 ("name-charset"), behaviour 2
("token-env-derivation"), behaviour 4 ("save-writes-record"), behaviour 5
("save-updates-in-place"), behaviour 6 ("save-renames-on-same-path"),
behaviour 7 ("save-refuses-name-collision"), behaviour 8
("save-refuses-token-value"), behaviour 9 ("load-unknown-name"),
behaviour 10 ("load-vanished-path") and behaviour 11
("two-profiles-coexist", including the ``list_profiles`` contract);
the later behaviours (``resolve_token``) will be added here as separate
test classes as they are implemented.

``piprofile`` is imported inside each test body rather than at collection
time, so the file always collects cleanly while the store behaviours remain
unimplemented: a missing ``save_profile`` surfaces as an ``AttributeError``
naming the function, not as a collection error in this file. ``yamlio`` is
imported at the top because it is already green.
"""

import importlib
import os
import shutil
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


# Behaviour 7: a store holding ``project-x`` at a real directory A, re-saved
# under the SAME name for a DIFFERENT real directory B. The write must be
# refused — a silent overwrite would leave a later run editing the wrong
# repository — and the refusal must name the existing path (A) so the
# operator learns which repository that name already points at. The values
# are owned by the tests.
COLLISION_NAME = "project-x"
COLLISION_IDENTITY = ("octo-org", "project-x", "main")


class SaveProfileRefusesNameCollisionTestCase(unittest.TestCase):
    """Behaviour 7: save-refuses-name-collision."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1, 2, 4, 5 and 6 are green), so the
        import succeeds and the assertions below surface as genuine
        failures against the store contents, not as an AttributeError.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def _save(self, module, root, name, target):
        owner, repo, base = COLLISION_IDENTITY
        module.save_profile(
            root=root,
            name=name,
            path=target,
            owner=owner,
            repo=repo,
            base=base,
            project={},
        )

    def _store_at(self, module, tmp):
        """Build two real directories and save ``project-x`` at the first.

        Returns ``(root, dir_a, dir_b)`` with the store holding
        ``COLLISION_NAME`` at ``dir_a``.
        """
        dir_a = Path(tmp) / "project-x"
        dir_a.mkdir()
        dir_b = Path(tmp) / "other"
        dir_b.mkdir()
        root = Path(tmp) / ".anvil"
        self._save(module, root, COLLISION_NAME, dir_a)
        return root, dir_a, dir_b

    def test_save_profile_same_name_different_path_raises_profile_error(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, _dir_a, dir_b = self._store_at(module, tmp)

            with self.assertRaises(module.ProfileError):
                self._save(module, root, COLLISION_NAME, dir_b)

    def test_save_profile_name_collision_error_names_existing_path(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, dir_a, dir_b = self._store_at(module, tmp)

            with self.assertRaises(module.ProfileError) as ctx:
                self._save(module, root, COLLISION_NAME, dir_b)

            # The EXISTING path (directory A, in the absolute form the
            # store records) is named so the operator learns which
            # repository that name already points at.
            self.assertIn(os.path.abspath(str(dir_a)), str(ctx.exception))

    def test_save_profile_same_name_different_path_leaves_store_untouched(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, dir_a, dir_b = self._store_at(module, tmp)
            store_path = root / "profiles.yaml"
            before = store_path.read_bytes()

            with self.assertRaises(module.ProfileError):
                self._save(module, root, COLLISION_NAME, dir_b)

            # Nothing on disk is touched: the store file is byte-identical
            # and the record still points at directory A, not B.
            self.assertEqual(store_path.read_bytes(), before)
            profile = yamlio.load(store_path)[COLLISION_NAME]
            self.assertEqual(profile["path"], os.path.abspath(str(dir_a)))


# Behaviour 8: the store records which key holds the token, never the token.
# The detection rule is decided and recorded in the plan's Assumptions
# (plans/pi-phase13-profiles.md): a record is refused when any string value
# in ``owner``, ``repo``, ``base`` or the ``project`` block starts with a
# known GitHub token prefix, and the ProfileError names the offending
# field. No length floor — the prefix is the rule. The profile's own
# ``token_env`` field is derived from the name and is never a smuggle-in
# vector, so it is deliberately not tested here.
TOKEN_PREFIXES = [
    "ghp_",
    "gho_",
    "ghu_",
    "ghs_",
    "ghr_",
    "github_pat_",
    "glpat_",
]

#: A token value per prefix: the prefix itself plus a plausible body, so no
#: implementation can pass by matching the prefix alone against an empty
#: remainder — the value still starts with the prefix either way.
def _token_value(prefix):
    return prefix + "abcdefghijklmnop"


#: The identity fields the rule covers, one per way of smuggling a token in
#: outside the ``project`` block.
TOKEN_IDENTITY_FIELDS = ["owner", "repo", "base"]

#: Ordinary values that merely resemble a token and must NOT be refused:
#: the prefix mid-sentence, or embedded after other characters. The rule is
#: start-of-string, not "contains" — so none of these may start with a
#: prefix, or the refusal rule would fire for good reason.
ORDINARY_OWNERS = ["notghp_abcdefghijklmnop", "xghu_abcdefgh"]
ORDINARY_STRUCTURE = "layout: see ghp_abcdefghijklmnop in the notes\n"
ORDINARY_CONFIGURATION = "gateway port 8080 (notglpat_abc is a label)"


class SaveProfileRefusesTokenValueTestCase(unittest.TestCase):
    """Behaviour 8: save-refuses-token-value."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1, 2, 4, 5, 6 and 7 are green), so
        the import succeeds and the assertions below surface as genuine
        failures — no ProfileError raised, the file written — not as an
        AttributeError: the token check is simply absent yet.
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

    def test_save_profile_token_value_in_identity_field_raises_profile_error(self):
        module = self._module()
        for prefix in TOKEN_PREFIXES:
            for field in TOKEN_IDENTITY_FIELDS:
                with self.subTest(prefix=prefix, field=field):
                    with tempfile.TemporaryDirectory() as tmp:
                        target = Path(tmp) / RECORD_NAME
                        target.mkdir()
                        root = Path(tmp) / ".anvil"

                        with self.assertRaises(module.ProfileError):
                            self._save(
                                module, root, target,
                                **{field: _token_value(prefix)},
                            )

    def test_save_profile_token_value_in_project_block_raises_profile_error(self):
        module = self._module()
        for prefix in TOKEN_PREFIXES:
            with self.subTest(prefix=prefix):
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / RECORD_NAME
                    target.mkdir()
                    root = Path(tmp) / ".anvil"

                    with self.assertRaises(module.ProfileError):
                        self._save(
                            module, root, target,
                            project={
                                "name": "project-x",
                                "structure": "flat",
                                "configuration": _token_value(prefix),
                            },
                        )

    def test_save_profile_token_value_error_names_offending_field(self):
        module = self._module()
        for prefix in TOKEN_PREFIXES:
            for field in TOKEN_IDENTITY_FIELDS:
                with self.subTest(prefix=prefix, field=field):
                    with tempfile.TemporaryDirectory() as tmp:
                        target = Path(tmp) / RECORD_NAME
                        target.mkdir()
                        root = Path(tmp) / ".anvil"

                        with self.assertRaises(module.ProfileError) as ctx:
                            self._save(
                                module, root, target,
                                **{field: _token_value(prefix)},
                            )

                        # The field is named so the operator knows which
                        # value to fix, not just that a save was refused.
                        self.assertIn(field, str(ctx.exception))

    def test_save_profile_token_value_in_project_block_error_names_field(self):
        module = self._module()
        with self.subTest(prefix="ghp_"):
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / RECORD_NAME
                target.mkdir()
                root = Path(tmp) / ".anvil"

                with self.assertRaises(module.ProfileError) as ctx:
                    self._save(
                        module, root, target,
                        project={"configuration": _token_value("ghp_")},
                    )

                self.assertIn("configuration", str(ctx.exception))

    def test_save_profile_token_value_writes_nothing_when_store_empty(self):
        module = self._module()
        for prefix in TOKEN_PREFIXES:
            for field in TOKEN_IDENTITY_FIELDS:
                with self.subTest(prefix=prefix, field=field):
                    with tempfile.TemporaryDirectory() as tmp:
                        target = Path(tmp) / RECORD_NAME
                        target.mkdir()
                        root = Path(tmp) / ".anvil"

                        with self.assertRaises(module.ProfileError):
                            self._save(
                                module, root, target,
                                **{field: _token_value(prefix)},
                            )

                        # Nothing is written: no store file, and no root
                        # directory created either — the check precedes any
                        # filesystem effect.
                        self.assertFalse((root / "profiles.yaml").exists())
                        self.assertFalse(root.exists())

    def test_save_profile_token_value_leaves_existing_store_byte_identical(self):
        module = self._module()
        for prefix in TOKEN_PREFIXES:
            for field in TOKEN_IDENTITY_FIELDS:
                with self.subTest(prefix=prefix, field=field):
                    with tempfile.TemporaryDirectory() as tmp:
                        target = Path(tmp) / RECORD_NAME
                        target.mkdir()
                        root = Path(tmp) / ".anvil"

                        # The store already holds a good record for the
                        # same name and path; the re-save smuggles a token.
                        self._save(module, root, target)
                        store_path = root / "profiles.yaml"
                        before = store_path.read_bytes()

                        with self.assertRaises(module.ProfileError):
                            self._save(
                                module, root, target,
                                **{field: _token_value(prefix)},
                            )

                        # The existing store file is byte-identical and the
                        # old record's good value survives the refusal.
                        self.assertEqual(store_path.read_bytes(), before)
                        profile = yamlio.load(store_path)[RECORD_NAME]
                        self.assertEqual(profile[field], {
                            "owner": RECORD_OWNER,
                            "repo": RECORD_REPO,
                            "base": RECORD_BASE,
                        }[field])

    def test_save_profile_ordinary_values_are_not_refused(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / RECORD_NAME
            target.mkdir()
            root = Path(tmp) / ".anvil"

            # Every value here merely resembles a token: a prefix after
            # other characters, or mid-sentence. None is a token, so the
            # save must succeed and round-trip the values as given.
            self._save(
                module, root, target,
                owner=ORDINARY_OWNERS[0],
                repo=ORDINARY_OWNERS[1],
                project={
                    "name": "project-x",
                    "structure": ORDINARY_STRUCTURE,
                    "configuration": ORDINARY_CONFIGURATION,
                },
            )

            profile = yamlio.load(root / "profiles.yaml")[RECORD_NAME]

            self.assertEqual(profile["owner"], ORDINARY_OWNERS[0])
            self.assertEqual(profile["repo"], ORDINARY_OWNERS[1])
            self.assertEqual(profile["base"], RECORD_BASE)
            self.assertEqual(
                profile["project"]["structure"], ORDINARY_STRUCTURE
            )
            self.assertEqual(
                profile["project"]["configuration"], ORDINARY_CONFIGURATION
            )

    def test_save_profile_prefix_match_is_start_of_string_only(self):
        module = self._module()
        for field in TOKEN_IDENTITY_FIELDS:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / RECORD_NAME
                    target.mkdir()
                    root = Path(tmp) / ".anvil"

                    # The prefix embedded after other characters is NOT a
                    # token: the match is by start of the string, and this
                    # save must succeed.
                    value = "not" + _token_value("ghp_")
                    self._save(
                        module, root, target,
                        **{field: value},
                    )

                    profile = yamlio.load(root / "profiles.yaml")[RECORD_NAME]
                    self.assertEqual(profile[field], value)


# Behaviour 9: ``load_profile(root, name)`` returns the stored record for a
# known name and fails naming the unknown name for a typo, listing the
# known profile names so the typo is fixable without reading the YAML. The
# values are owned by the tests; the store is seeded through the green
# ``save_profile`` at real directories so the read is proven against a
# store the write path produced, not a hand-written file.
LOAD_PROJECT_IDENTITY = ("octo-org", "project-x", "main")
LOAD_API_IDENTITY = ("api-org", "api", "master")

#: The populated project block the ``project-x`` record carries; ``api``
#: carries an empty block, so both shapes of behaviour 12 are loaded.
LOAD_PROJECT_BLOCK = {
    "name": "project-x",
    "structure": "anvilkit/   python package\nplans/    decision record\n",
    "configuration": "gateway port 8080\ncontext 32k",
}

#: A name the store does not hold.
LOAD_UNKNOWN_NAME = "typo"


class LoadProfileUnknownNameTestCase(unittest.TestCase):
    """Behaviour 9: load-unknown-name."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1, 2, 4, 5, 6, 7 and 8 are green), so
        the import succeeds and a missing ``load_profile`` surfaces as an
        ``AttributeError`` naming the function, not as a collection error.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def _seed_two_profiles(self, module, tmp):
        """Seed the store with ``project-x`` and ``api`` at real dirs.

        ``project-x`` carries the populated ``LOAD_PROJECT_BLOCK``; ``api``
        carries an empty project block. Returns ``(root, dir_x, dir_api)``.
        """
        dir_x = Path(tmp) / "project-x"
        dir_x.mkdir()
        dir_api = Path(tmp) / "api"
        dir_api.mkdir()
        root = Path(tmp) / ".anvil"
        module.save_profile(
            root=root,
            name="project-x",
            path=dir_x,
            owner=LOAD_PROJECT_IDENTITY[0],
            repo=LOAD_PROJECT_IDENTITY[1],
            base=LOAD_PROJECT_IDENTITY[2],
            project=LOAD_PROJECT_BLOCK,
        )
        module.save_profile(
            root=root,
            name="api",
            path=dir_api,
            owner=LOAD_API_IDENTITY[0],
            repo=LOAD_API_IDENTITY[1],
            base=LOAD_API_IDENTITY[2],
            project={},
        )
        return root, dir_x, dir_api

    def test_load_profile_known_name_returns_record_with_fields_intact(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, dir_x, dir_api = self._seed_two_profiles(module, tmp)

            for name, target, identity, project in (
                ("project-x", dir_x, LOAD_PROJECT_IDENTITY, LOAD_PROJECT_BLOCK),
                ("api", dir_api, LOAD_API_IDENTITY, {}),
            ):
                with self.subTest(name=name):
                    record = module.load_profile(root, name)

                    self.assertEqual(
                        record["path"], os.path.abspath(str(target))
                    )
                    self.assertEqual(record["owner"], identity[0])
                    self.assertEqual(record["repo"], identity[1])
                    self.assertEqual(record["base"], identity[2])
                    # The derivation behaviour 2 pins, through the module's
                    # own function so the test pins the contract, not a copy.
                    self.assertEqual(
                        record["token_env"], module.token_env_for(name)
                    )
                    self.assertEqual(record["project"], project)

    def test_load_profile_unknown_name_raises_profile_error_naming_name_and_listing_known(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, _dir_x, _dir_api = self._seed_two_profiles(module, tmp)

            with self.assertRaises(module.ProfileError) as ctx:
                module.load_profile(root, LOAD_UNKNOWN_NAME)

            # The typo is named, and both known names are listed so the
            # operator can fix the name without reading the YAML.
            message = str(ctx.exception)
            self.assertIn(LOAD_UNKNOWN_NAME, message)
            self.assertIn("project-x", message)
            self.assertIn("api", message)

    def test_load_profile_missing_store_raises_profile_error_for_any_name(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            # The root directory does not exist at all: no profiles.yaml.
            root = Path(tmp) / ".anvil"
            self.assertFalse(root.exists())

            # (requested name, known names that must NOT appear in the
            # message — the empty store invents none).
            for name, absent_known in (
                ("project-x", ["api"]),
                ("api", ["project-x"]),
                ("typo", ["project-x", "api"]),
            ):
                with self.subTest(name=name):
                    with self.assertRaises(module.ProfileError) as ctx:
                        module.load_profile(root, name)

                    message = str(ctx.exception)
                    self.assertIn(name, message)
                    for known in absent_known:
                        self.assertNotIn(known, message)

            # A read is a read: the failed load created nothing, neither
            # the store file nor the root directory.
            self.assertFalse((root / "profiles.yaml").exists())
            self.assertFalse(root.exists())

    def test_load_profile_empty_store_raises_profile_error_for_any_name(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            # The root exists but holds no profiles.yaml.
            root = Path(tmp) / ".anvil"
            root.mkdir()

            for name, absent_known in (
                ("project-x", ["api"]),
                ("api", ["project-x"]),
                ("typo", ["project-x", "api"]),
            ):
                with self.subTest(name=name):
                    with self.assertRaises(module.ProfileError) as ctx:
                        module.load_profile(root, name)

                    message = str(ctx.exception)
                    self.assertIn(name, message)
                    for known in absent_known:
                        self.assertNotIn(known, message)

            # The failed load did not invent a store file.
            self.assertFalse((root / "profiles.yaml").exists())


# Behaviour 10: a stored profile whose ``path`` no longer exists on disk.
# The store is seeded through the green ``save_profile`` at a real
# directory, then that directory is deleted — ``load_profile`` must refuse
# to hand a caller a record pointing at a missing directory. The values are
# owned by the tests.
VANISHED_NAME = "project-x"
VANISHED_IDENTITY = ("octo-org", "project-x", "main")

#: The second record's identity, at a directory that SURVIVES the deletion.
VANISHED_SIBLING_NAME = "api"
VANISHED_SIBLING_IDENTITY = ("api-org", "api", "master")


class LoadProfileVanishedPathTestCase(unittest.TestCase):
    """Behaviour 10: load-vanished-path."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1 through 9 are green), so the import
        succeeds and a missing path check surfaces as a genuine failure —
        the record comes back, no ``ProfileError`` — not as an
        ``AttributeError``.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def _seed_with_vanished_path(self, module, tmp):
        """Seed two profiles, then delete the first one's directory.

        Both are saved through the green ``save_profile`` at real
        directories; ``VANISHED_NAME``'s directory is then removed with
        ``shutil.rmtree`` while ``VANISHED_SIBLING_NAME``'s survives.
        Returns ``(root, vanished_dir, sibling_dir)``.
        """
        vanished_dir = Path(tmp) / VANISHED_NAME
        vanished_dir.mkdir()
        sibling_dir = Path(tmp) / VANISHED_SIBLING_NAME
        sibling_dir.mkdir()
        root = Path(tmp) / ".anvil"
        module.save_profile(
            root=root,
            name=VANISHED_NAME,
            path=vanished_dir,
            owner=VANISHED_IDENTITY[0],
            repo=VANISHED_IDENTITY[1],
            base=VANISHED_IDENTITY[2],
            project={},
        )
        module.save_profile(
            root=root,
            name=VANISHED_SIBLING_NAME,
            path=sibling_dir,
            owner=VANISHED_SIBLING_IDENTITY[0],
            repo=VANISHED_SIBLING_IDENTITY[1],
            base=VANISHED_SIBLING_IDENTITY[2],
            project={},
        )
        # The first record's directory is gone; the sibling's survives.
        shutil.rmtree(vanished_dir)
        self.assertFalse(vanished_dir.exists())
        self.assertTrue(sibling_dir.exists())
        return root, vanished_dir, sibling_dir

    def test_load_profile_vanished_path_raises_profile_error(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, _vanished_dir, _sibling_dir = self._seed_with_vanished_path(
                module, tmp
            )

            # The caller never receives a record pointing at a missing
            # directory: assertRaises fails if load_profile returns.
            with self.assertRaises(module.ProfileError):
                module.load_profile(root, VANISHED_NAME)

    def test_load_profile_vanished_path_error_names_profile_and_path(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, vanished_dir, _sibling_dir = self._seed_with_vanished_path(
                module, tmp
            )

            with self.assertRaises(module.ProfileError) as ctx:
                module.load_profile(root, VANISHED_NAME)

            # The error is about the path, not the name: the name IS in the
            # store, but the message must still name the profile as well as
            # the vanished path (in the absolute form the store records).
            message = str(ctx.exception)
            self.assertIn(VANISHED_NAME, message)
            self.assertIn(os.path.abspath(str(vanished_dir)), message)

    def test_load_profile_sibling_survives_vanished_sibling_path(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, _vanished_dir, sibling_dir = self._seed_with_vanished_path(
                module, tmp
            )

            # The check is per-record, not a store-wide scan that fails the
            # whole load: the surviving profile loads with its fields intact
            # even though its sibling's path has vanished.
            record = module.load_profile(root, VANISHED_SIBLING_NAME)

            self.assertEqual(
                record["path"], os.path.abspath(str(sibling_dir))
            )
            self.assertEqual(record["owner"], VANISHED_SIBLING_IDENTITY[0])
            self.assertEqual(record["repo"], VANISHED_SIBLING_IDENTITY[1])
            self.assertEqual(record["base"], VANISHED_SIBLING_IDENTITY[2])


# Behaviour 11: two provisionings at distinct paths under distinct owners
# coexist in one store — one Anvil install serving many repositories is the
# whole point. Both records are seeded through the green ``save_profile`` at
# real directories and read back through the green ``load_profile``; the
# store must hold both, each with its own ``path``, ``owner``, ``repo`` and
# ``token_env``. ``list_profiles`` (the only piece of this behaviour that is
# not yet implemented) must return both names sorted, and an empty or
# missing store must give an empty list, not an error. The values are owned
# by the tests.
COEXIST_X_NAME = "project-x"
COEXIST_X_IDENTITY = ("alpha", "project-x", "main")
COEXIST_X_PROJECT_BLOCK = {
    "name": "project-x",
    "structure": "anvilkit/   python package\nplans/    decision record\n",
    "configuration": "gateway port 8080\ncontext 32k",
}
COEXIST_API_NAME = "api"
COEXIST_API_IDENTITY = ("beta", "api", "master")


class TwoProfilesCoexistTestCase(unittest.TestCase):
    """Behaviour 11: two-profiles-coexist."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1 through 10 are green), so the
        import succeeds and the missing ``list_profiles`` surfaces as an
        ``AttributeError`` naming the function, not as a collection
        error; the coexistence save/load half is asserted against the
        store the green write and read paths produced.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def _seed_two_profiles(self, module, tmp):
        """Seed one store with both provisionings at real directories.

        ``project-x`` at owner ``alpha`` with the populated project block,
        ``api`` at owner ``beta`` with an empty block — distinct paths,
        distinct owners, one store. Returns ``(root, dir_x, dir_api)``.
        """
        dir_x = Path(tmp) / COEXIST_X_NAME
        dir_x.mkdir()
        dir_api = Path(tmp) / COEXIST_API_NAME
        dir_api.mkdir()
        root = Path(tmp) / ".anvil"
        module.save_profile(
            root=root,
            name=COEXIST_X_NAME,
            path=dir_x,
            owner=COEXIST_X_IDENTITY[0],
            repo=COEXIST_X_IDENTITY[1],
            base=COEXIST_X_IDENTITY[2],
            project=COEXIST_X_PROJECT_BLOCK,
        )
        module.save_profile(
            root=root,
            name=COEXIST_API_NAME,
            path=dir_api,
            owner=COEXIST_API_IDENTITY[0],
            repo=COEXIST_API_IDENTITY[1],
            base=COEXIST_API_IDENTITY[2],
            project={},
        )
        return root, dir_x, dir_api

    def test_save_profile_two_provisionings_store_holds_both_records(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, dir_x, dir_api = self._seed_two_profiles(module, tmp)

            record = yamlio.load(root / "profiles.yaml")

            # One store, two profiles, no third key invented.
            self.assertEqual(record["version"], 1)
            self.assertEqual(
                sorted(k for k in record if k != "version"),
                [COEXIST_API_NAME, COEXIST_X_NAME],
            )
            # Each record keeps its own identity, not the other's.
            profile_x = record[COEXIST_X_NAME]
            self.assertEqual(
                profile_x["path"], os.path.abspath(str(dir_x))
            )
            self.assertEqual(profile_x["owner"], COEXIST_X_IDENTITY[0])
            self.assertEqual(profile_x["repo"], COEXIST_X_IDENTITY[1])
            self.assertEqual(
                profile_x["token_env"], module.token_env_for(COEXIST_X_NAME)
            )
            profile_api = record[COEXIST_API_NAME]
            self.assertEqual(
                profile_api["path"], os.path.abspath(str(dir_api))
            )
            self.assertEqual(profile_api["owner"], COEXIST_API_IDENTITY[0])
            self.assertEqual(profile_api["repo"], COEXIST_API_IDENTITY[1])
            self.assertEqual(
                profile_api["token_env"], module.token_env_for(COEXIST_API_NAME)
            )

    def test_load_profile_both_records_load_back_intact(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, dir_x, dir_api = self._seed_two_profiles(module, tmp)

            # Saving the second provisioning did not clobber the first:
            # each profile loads back through the green load_profile with
            # its own fields intact, through the module's own derivation
            # so the test pins the contract, not a copy.
            for name, target, identity, project in (
                (COEXIST_X_NAME, dir_x, COEXIST_X_IDENTITY,
                 COEXIST_X_PROJECT_BLOCK),
                (COEXIST_API_NAME, dir_api, COEXIST_API_IDENTITY, {}),
            ):
                with self.subTest(name=name):
                    record = module.load_profile(root, name)

                    self.assertEqual(
                        record["path"], os.path.abspath(str(target))
                    )
                    self.assertEqual(record["owner"], identity[0])
                    self.assertEqual(record["repo"], identity[1])
                    self.assertEqual(record["base"], identity[2])
                    self.assertEqual(
                        record["token_env"], module.token_env_for(name)
                    )
                    self.assertEqual(record["project"], project)

    def test_list_profiles_two_profiles_returns_both_names_sorted(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            root, _dir_x, _dir_api = self._seed_two_profiles(module, tmp)

            # Both names, exactly, in sorted order: "api" before
            # "project-x" regardless of the order they were saved.
            self.assertEqual(
                module.list_profiles(root),
                [COEXIST_API_NAME, COEXIST_X_NAME],
            )

    def test_list_profiles_missing_store_returns_empty_list(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            # The root does not exist at all: no profiles.yaml. An empty
            # list, not an error, is the contract.
            root = Path(tmp) / ".anvil"
            self.assertFalse(root.exists())

            self.assertEqual(module.list_profiles(root), [])

            # A read is a read: the failed-free listing created nothing.
            self.assertFalse((root / "profiles.yaml").exists())
            self.assertFalse(root.exists())

    def test_list_profiles_empty_store_returns_empty_list(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            # The root exists but holds no profiles.yaml.
            root = Path(tmp) / ".anvil"
            root.mkdir()

            self.assertEqual(module.list_profiles(root), [])

            # The listing did not invent a store file.
            self.assertFalse((root / "profiles.yaml").exists())


# Behaviour 12: the project block round-trips byte-identically. The values
# are owned by the tests and are the ones the byte-identity claim must
# survive: ``structure`` ends in a trailing newline, and
# ``configuration`` contains a blank line (consecutive newlines) — a store
# that dropped either newline or collapsed the blank line would fail the
# round-trip. A project block that is not a mapping must be refused with a
# ``ProfileError`` naming the project field, writing nothing.
ROUNDTRIP_NAME = "roundtrip-proj"
ROUNDTRIP_IDENTITY = ("gamma", "roundtrip-proj", "main")
ROUNDTRIP_PROJECT_BLOCK = {
    "name": "roundtrip-proj",
    # Trailing newline: the value ends in \n and must come back ending in \n.
    "structure": "anvilkit/   python package\nplans/    decision record\n",
    # Consecutive newlines: the blank line must survive, not collapse.
    "configuration": "gateway port 8080\n\ncontext 32k\n",
}

#: Project blocks that are not mappings: a string and a list, one per way a
#: caller could hand over the wrong shape.
NON_MAPPING_PROJECT_BLOCKS = [
    "a block",
    ["structure", "configuration"],
]


class ProjectBlockRoundtripTestCase(unittest.TestCase):
    """Behaviour 12: project-block-roundtrip."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviours 1 through 11 are green), so the import
        succeeds and the assertions run against the store the green write and
        read paths produce; the non-mapping refusal is the new contract under
        test.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def _save_block(self, module, root, target, block):
        return module.save_profile(
            root=root,
            name=ROUNDTRIP_NAME,
            path=target,
            owner=ROUNDTRIP_IDENTITY[0],
            repo=ROUNDTRIP_IDENTITY[1],
            base=ROUNDTRIP_IDENTITY[2],
            project=block,
        )

    def test_save_profile_project_block_roundtrip_loads_back_byte_identical(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ROUNDTRIP_NAME
            target.mkdir()
            root = Path(tmp) / ".anvil"

            self._save_block(module, root, target, ROUNDTRIP_PROJECT_BLOCK)
            record = module.load_profile(root, ROUNDTRIP_NAME)

            # The whole block, exactly: a dropped trailing newline, a
            # collapsed blank line or a missing field all fail.
            self.assertEqual(record["project"], ROUNDTRIP_PROJECT_BLOCK)
            for field, expected in ROUNDTRIP_PROJECT_BLOCK.items():
                with self.subTest(field=field):
                    self.assertEqual(record["project"][field], expected)
            # The rest of the record comes back with it.
            self.assertEqual(record["path"], os.path.abspath(str(target)))
            self.assertEqual(record["owner"], ROUNDTRIP_IDENTITY[0])
            self.assertEqual(record["repo"], ROUNDTRIP_IDENTITY[1])
            self.assertEqual(record["base"], ROUNDTRIP_IDENTITY[2])
            self.assertEqual(
                record["token_env"], module.token_env_for(ROUNDTRIP_NAME)
            )

    def test_save_profile_empty_project_block_loads_back_as_empty_mapping(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ROUNDTRIP_NAME
            target.mkdir()
            root = Path(tmp) / ".anvil"

            self._save_block(module, root, target, {})
            record = module.load_profile(root, ROUNDTRIP_NAME)

            # An empty block is valid, not an error: it loads back as the
            # empty mapping, present in the record.
            self.assertIn("project", record)
            self.assertEqual(record["project"], {})

    def test_save_profile_non_mapping_project_block_raises_profile_error_naming_project(self):
        module = self._module()
        for block in NON_MAPPING_PROJECT_BLOCKS:
            with self.subTest(block=block):
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / ROUNDTRIP_NAME
                    target.mkdir()
                    root = Path(tmp) / ".anvil"

                    with self.assertRaises(module.ProfileError) as ctx:
                        self._save_block(module, root, target, block)

                    # The error names the project field, so the operator
                    # knows which value to fix without reading the store.
                    self.assertIn("project", str(ctx.exception))

    def test_save_profile_non_mapping_project_block_writes_nothing_to_fresh_root(self):
        module = self._module()
        for block in NON_MAPPING_PROJECT_BLOCKS:
            with self.subTest(block=block):
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / ROUNDTRIP_NAME
                    target.mkdir()
                    root = Path(tmp) / ".anvil"
                    self.assertFalse(root.exists())

                    with self.assertRaises(module.ProfileError):
                        self._save_block(module, root, target, block)

                    # A refusal that left a store behind would record a
                    # broken profile the next load chokes on: for a fresh
                    # root the store file must not come into existence.
                    self.assertFalse((root / "profiles.yaml").exists())

    def test_save_profile_non_mapping_project_block_leaves_existing_record_untouched(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ROUNDTRIP_NAME
            target.mkdir()
            root = Path(tmp) / ".anvil"
            self._save_block(module, root, target, ROUNDTRIP_PROJECT_BLOCK)
            # Snapshot the raw store before the refused re-save.
            before = yamlio.load(root / "profiles.yaml")

            for block in NON_MAPPING_PROJECT_BLOCKS:
                with self.subTest(block=block):
                    with self.assertRaises(module.ProfileError):
                        self._save_block(module, root, target, block)

                    # The re-save was refused before any write: the stored
                    # record is byte-for-byte the one that was there,
                    # project block included, and still loads back intact.
                    self.assertEqual(
                        yamlio.load(root / "profiles.yaml"), before
                    )
                    self.assertEqual(
                        module.load_profile(root, ROUNDTRIP_NAME)["project"],
                        ROUNDTRIP_PROJECT_BLOCK,
                    )
