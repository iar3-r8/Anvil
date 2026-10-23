# Creating rulesets for a repository — GitHub Docs

Source: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository
Fetched: 2026-10-23 (docs.github.com HTML, main region)

In this article 
# Creating rulesets for a repository You can add rulesets to a repository to control how people can interact with specific branches and tags. Copy markdown 
## Who can use this feature? Anyone with read access to a repository can view the repository's rulesets. People with admin access to a repository, or a custom role with the "edit repository rules" permission, can create, edit, and delete rulesets for a repository. Rulesets are available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, and GitHub Enterprise Cloud. See GitHub's plans . 
 Push rulesets are available for the GitHub Team plan in internal and private repositories, and forks of repositories that have push rulesets enabled. 
## In this article 
- Introduction 
- Importing prebuilt rulesets 
- Using fnmatch syntax 
- Using ruleset enforcement statuses 
- Creating a branch or tag ruleset 
- Creating a push ruleset 
## Introduction 
 You can create rulesets to control how users can interact with selected branches and tags in a repository. You can control things like who can push commits to a certain branch and how the commits must be formatted, or who can delete or rename a tag. You can also prevent people from renaming repositories. 
 You can also create push rulesets to block pushes to a private or internal repository and the repository's entire fork network. Push rulesets allow you to block pushes based on file extensions, file path lengths, file and folder paths, and file sizes. 
 When you create a ruleset, you can allow certain users to bypass the rules in the ruleset. 
 For more information on rulesets, see About rulesets . 
 For customers on GitHub Team and GitHub Enterprise plans you can also create rulesets for repositories in an organization. For more information, see Creating rulesets for repositories in your organization . 

## Importing prebuilt rulesets 
 To import one of the prebuilt rulesets by GitHub, see github/ruleset-recipes . 
 You can import an existing ruleset using a JSON file. This can be useful if you want to apply the same ruleset to multiple repositories or organizations. For more information, see Managing rulesets for repositories in your organization . 

## Using fnmatch syntax 
 You can use fnmatch syntax to define patterns to target when you create a ruleset. 
 You can use the * wildcard to match any string of characters. Because GitHub uses the File::FNM_PATHNAME flag for the File.fnmatch syntax, the * wildcard does not match directory separators ( / ). For example, qa/* will match all branches beginning with qa/ and containing a single slash, but will not match qa/foo/bar . You can include any number of slashes after qa with qa/**/* , which would match, for example, qa/foo/bar/foobar/hello-world . You can also extend the qa string with qa**/**/* to make the rule more inclusive. 
 For more information about syntax options, see the fnmatch documentation . 

### Unsupported fnmatch syntax 
 Not all expressions from the fnmatch syntax are supported in branch protection rules. Please be aware of the following constraints: 

- You cannot use the backslash ( \ ) character as a quoting character, as GitHub does not support the use of backslashes in branch protection rules. 

- You can specify character sets within square brackets ( [] ), but you cannot currently complement a set with the ^ operator (e.g., [^charset] ). 

- Although GitHub supports File::FNM_PATHNAME in fnmatch syntax, File::FNM_EXTGLOB is not supported. 

## Using ruleset enforcement statuses 
 While creating or editing your ruleset, you can use enforcement statuses to configure how your ruleset will be enforced. 
 You can select any of the following enforcement statuses for your ruleset. 

- Active: your ruleset will be enforced upon creation. 

- Disabled: your ruleset will not be enforced. 

## Creating a branch or tag ruleset 

- 
 On GitHub, navigate to the main page of the repository. 

- 
 Under your repository name, click Settings . If you cannot see the "Settings" tab, select the dropdown menu, then click Settings . 

- 
 In the left sidebar, under "Code, planning, and automation", click Rulesets , then click Rulesets . 

- 
 Click New ruleset . 

- 
 To create a ruleset targeting branches, click New branch ruleset . Alternatively, to create a ruleset targeting tags, click New tag ruleset . 

- 
 Under "Ruleset name," type a name for the ruleset. 

- 
 Optionally, to change the default enforcement status, click Disabled and select an enforcement status. 

### Granting bypass permissions for your branch or tag ruleset 
 You can grant certain roles, teams, or apps bypass permissions for your ruleset. The following are eligible for bypass access: 

- Repository admins, organization owners, and enterprise owners 

- The maintain or write role, or custom repository roles based on the write role 

- Teams, excluding secret teams. See About organization teams . 

- GitHub Apps 

- Dependabot. For more information about Dependabot, see Dependabot quickstart guide . 

- 
 To grant bypass permissions for the ruleset, in the "Bypass list" section, click Add bypass . 

- 
 In the "Add bypass" modal dialog that appears, search for the role, team, or app you would like to grant bypass permissions, then select the role, team, or app from the "Suggestions" section and click Add Selected . 

- 
 Optionally, to grant bypass to an actor without allowing them to push directly to a repository, to the right of "Always allow," click , then click For pull requests only . 
 The selected actor is now required to open a pull request to make changes to a repository, creating a clear trail of their changes in the pull request and audit log. The actor can then choose to bypass any branch protections and merge that pull request. 

### Choosing which branches or tags to target 
 To target branches or tags, in the "Target branches" or "Target tags" section, select Add a target , then select how you want to include or exclude branches or tags. You can use fnmatch syntax to include or exclude branches or tags based on a pattern. For more information, see Using fnmatch syntax . 
 You can add multiple targeting criteria to the same ruleset. For example, you could include the default branch, include any branches matching the pattern *feature* , and then specifically exclude a branch matching the pattern not-a-feature . 

### Selecting branch or tag protections 
 In the "Branch protections" or "Tag protections" section, select the rules you want to include in the ruleset. When you select a rule, you may be able to enter additional settings for the rule. For more information on the rules, see Available rules for rulesets . 
 Note 

If you select Require status checks before merging , in the "Additional settings" section: 

- You can enter the name of each status check you would like to require. To finish adding the status check as a requirement, you must click . 

- If you select Require branches to be up to date before merging , you must define a check for the protection to take effect. 

### Adding metadata restrictions 
 Your metadata restrictions should be intended to increase consistency between commits in your repository. They are not intended to replace security measures such as requiring code review via pull requests. 
 Note 

If you squash merge a branch, all commits on that branch must meet any metadata requirements for the base branch. 
 When using end-of-line anchors in regular expressions, use \n?$ rather than $ alone. The optional \n? matches a trailing newline that may be present in Git push/CLI flows, while still working for commits created via the web UI and API. 

- 
 To add a rule to control commit metadata or branch names, in the "Restrictions" section when creating or editing a ruleset, click Restrict commit metadata or Restrict branch names . 

- 
 Configure the settings for the restriction, then click Add . You can add multiple restrictions to the same ruleset. 

- 
 To match a given regex pattern, in the "Requirement" dropdown, select Must match a given regex pattern . 
 For most requirements, such as "Must start with a matching pattern," the pattern you enter is interpreted literally, and wildcards are not supported. For example, the * character only represents the literal * character. 
 For more complex patterns, you can select "Must match a given regex pattern" or "Must not match a given regex pattern," then use regular expression syntax to define the matching pattern. For more information, see About regular expressions for commit metadata " in the GitHub Enterprise Cloud documentation. 
 Anyone who views the rulesets for a repository will be able to see the description you provide. 

- 
 Optionally, before enacting your ruleset with metadata restrictions, select the "Evaluate" enforcement status for your ruleset to test the effects of any metadata restrictions without impacting contributors. For more information on metadata restrictions, see Available rules for rulesets . 

### Finalizing your branch or tag ruleset and next steps 
 To finish creating your ruleset, click Create . If the enforcement status of the ruleset is set to "Active", the ruleset takes effect immediately. 

## Creating a push ruleset 
 Note 

This ruleset will enforce push restrictions for a repository's entire fork network. 

 You can create a push ruleset for private or internal repositories. 

- 
 On GitHub, navigate to the main page of the repository. 

- 
 Under your repository name, click Settings . If you cannot see the "Settings" tab, select the dropdown menu, then click Settings . 

- 
 In the left sidebar, under "Code, planning, and automation", click Rulesets , then click Rulesets . 

- 
 Click New ruleset . 

- 
 To create a ruleset targeting branches, click New push ruleset . 

- 
 Under "Ruleset name," type a name for the ruleset. 

- 
 Optionally, to change the default enforcement status, click Disabled and select an enforcement status. 

### Granting bypass permissions for your push ruleset 
 Note 
 Bypass permissions for push rulesets in this repository will be inherited by the entire fork network for this repository. This means that the only users who can bypass this ruleset for any repository in this repository's entire fork network are the users who can bypass this ruleset in the root repository. 

 You can grant certain roles, teams, or apps bypass permissions for your ruleset. The following are eligible for bypass access: 

- Repository admins, organization owners, and enterprise owners 

- The maintain or write role, or custom repository roles based on the write role 

- Teams, excluding secret teams. See About organization teams . 

- GitHub Apps 

- Dependabot. For more information about Dependabot, see Dependabot quickstart guide . 

- To grant bypass permissions for the ruleset, in the "Bypass list" section, click Add bypass . 

- In the "Add bypass" modal dialog that appears, search for the role, team, or app you would like to grant bypass permissions, then select the role, team, or app from the "Suggestions" section and click Add Selected . 

### Selecting push protections 
 You can block pushes to this repository and this repository's entire fork network based on file extensions, file path lengths, file and folder paths, and file sizes. 
 Any push protections you configure will block pushes in this repository and throughout this repository's entire fork network. 

- 
 Under "Push protections," click the restrictions you want to apply. Then fill in the details for the restrictions you select. 
 For file path restrictions, you can use partial or full paths. You can use fnmatch syntax for this. For example, a restriction targeting test/demo/**/* prevents any pushes to files or folders in the test/demo/ directory. A restriction targeting test/docs/pushrules.md prevents pushes specifically to the pushrules.md file in the test/docs/ directory. For more information, see Creating rulesets for a repository . 

- 
 Optionally, for the "Restrict file paths" and "Restrict file size" restrictions, under "Allowed exceptions," add the file paths you want to exempt from the restriction. 
 Allowed exceptions use fnmatch syntax and are validated when you save the ruleset. For example, **/gradle/wrapper/*.jar allows the Gradle wrapper JAR file in any directory. 

### Finalizing your push ruleset and next steps 
 To finish creating your ruleset, click Create . If the enforcement status of the ruleset is set to "Active", the ruleset takes effect immediately.
