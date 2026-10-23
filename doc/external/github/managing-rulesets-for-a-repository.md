# Managing rulesets for a repository — GitHub Docs

Source: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository
Fetched: 2026-10-23 (docs.github.com HTML, main region)

In this article 
# Managing rulesets for a repository You can edit, monitor, and delete existing rulesets in a repository to alter how people can interact with specific branches and tags. Copy markdown 
## Who can use this feature? Anyone with read access to a repository can view the repository's rulesets. People with admin access to a repository, or a custom role with the "edit repository rules" permission, can create, edit, and delete rulesets for a repository. Rulesets are available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, and GitHub Enterprise Cloud. See GitHub's plans . 
 Push rulesets are available for the GitHub Team plan in internal and private repositories, and forks of repositories that have push rulesets enabled. 
## In this article 
- Viewing rulesets for a repository 
- Editing a ruleset 
- Deleting a ruleset 
- Importing a ruleset 
- Viewing insights for rulesets After creating a ruleset, you can still make changes to it. For example, you can add rules to better protect your branches or tags, or you can temporarily disable a ruleset to troubleshoot any unintended effects on the contributor experience for your repository. 
 You can use the REST and GraphQL APIs to manage rulesets. For more information, see REST API endpoints for rules and Repositories . 

## Viewing rulesets for a repository 
 On the "Rulesets" page, anyone with read access to the repository can view the active rulesets targeting a certain branch, tag, or push restriction. 
 For push rulesets for forked repositories, the "Rulesets" page will indicate that the ruleset is managed by the source repository where the rule is applied. 

- 
 On GitHub, navigate to the main page of the repository. 

- 
 From the file tree view on the left, select the branch dropdown menu, then click View all branches . You can also find the branch dropdown menu at the top of the integrated file editor. 

- 
 To the right of the branch name, click . 
 Tip 
 Only branches that have a ruleset have a icon adjacent to their name. 

- 
 Optionally, to filter the results click the tabs or use the "Search branches" search bar. 

- 
 Click the name of the ruleset you want to view. 

 You can also view active rulesets: 

- 
 By adding the /rules slug to the repository's URL. For example, to view the rules of the open source documentation repository at GitHub, you would go to https://github.com/github/docs/rules . 

- 
 In the merge box if there are rules blocking the merging of a pull request. 

## Editing a ruleset 
 You can edit a ruleset to change parts of the ruleset, such as the name, bypass permissions, or rules. You can also edit a ruleset to change its status, such as if you want to enable or temporarily disable a ruleset. 

- 
 On GitHub, navigate to the main page of the repository. 

- 
 Under your repository name, click Settings . If you cannot see the "Settings" tab, select the dropdown menu, then click Settings . 

- 
 In the left sidebar, under "Code, planning, and automation", click Rulesets , then click Rulesets . 

- 
 On the "Rulesets" page, click the name of the ruleset you want to edit. 

- 
 Change the ruleset as required. For information on the available rules, see Available rules for rulesets . 

- 
 At the bottom of the page, click Save changes . 

## Deleting a ruleset 
 Tip 

If you want to temporarily disable a ruleset but do not want to delete it, you can set the ruleset's status to "Disabled." For more information, see Editing a ruleset . 

- 
 On GitHub, navigate to the main page of the repository. 

- 
 Under your repository name, click Settings . If you cannot see the "Settings" tab, select the dropdown menu, then click Settings . 

- 
 In the left sidebar, under "Code, planning, and automation", click Rulesets , then click Rulesets . 

- 
 Click the name of the ruleset you want to delete. 

- 
 To the right of the ruleset's name, select , then click Delete ruleset . 

## Importing a ruleset 
 You can import an existing ruleset using a JSON file. This can be useful if you want to apply the same ruleset to multiple repositories or organizations. 

- 
 On GitHub, navigate to the main page of the repository. 

- 
 Under your repository name, click Settings . If you cannot see the "Settings" tab, select the dropdown menu, then click Settings . 

- 
 In the left sidebar, under "Code, planning, and automation", click Rulesets , then click Rulesets . 

- 
 Select the New ruleset dropdown, then click Import a ruleset . 

- 
 Open the exported JSON file. 

- 
 Review the imported ruleset and click Create . 

## Viewing insights for rulesets 
 You can view insights for rulesets to see how rulesets are affecting a repository. On the "Rule Insights" page, you will see a timeline of the following user actions. You can use filters to find what you're looking for. 

- Actions that have been checked against one or more rulesets and passed. 

- Actions that have been checked against one or more rulesets and failed. 

- Actions where someone has bypassed one or more rulesets. 

 If a ruleset is running in "Evaluate" mode, you can see actions that would have passed or failed if the ruleset had been active. 
 Additionally, these insights are available via the rule suites REST API . 

- 
 On GitHub, navigate to the main page of the repository. 

- 
 Under your repository name, click Settings . If you cannot see the "Settings" tab, select the dropdown menu, then click Settings . 

- 
 In the left sidebar, under "Code and automation," click Rules , then click Insights . 

- 
 On the "Rule Insights" page, use the dropdown menus at the top of the page to filter the actions by ruleset, branch, actor, and time period. 

- 
 To see which specific rules failed or required a bypass, click , then expand the name of the ruleset. 

### Viewing the rule insights dashboard 
 Note 

The rule insights dashboard is available for GitHub Team and GitHub Enterprise Cloud plans. 

 The rule insights dashboard gives you a visual, high-level summary of rule evaluation activity for your repository, including: 

- Successes, failures, and bypasses over time : A chart showing trends in rule evaluation results, helping you spot spikes in blocked pushes or unusual patterns. 

- Top bypassers : A list of the most active bypassers for your rulesets. 

 Each chart links back to the rule insights page with filters prefilled, so you can quickly drill into specific statuses, bypassers, or time ranges. 
 To view the dashboard: 

- 
 On GitHub, navigate to the main page of the repository. 

- 
 Under your repository name, click Settings . If you cannot see the "Settings" tab, select the dropdown menu, then click Settings . 

- 
 In the left sidebar, under "Code and automation," click Rules , then click Insights . 

- 
 At the top of the "Rule Insights" page, view the dashboard charts for an overview of rule evaluation activity. 

 At the organization level, you can view the rule insights dashboard to review the evaluation activity of rulesets across your organization. See Managing rulesets for repositories in your organization .
