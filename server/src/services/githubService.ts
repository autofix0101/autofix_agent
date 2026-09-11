import axios from "axios";

export const getGithubAuthUrl = () => {
    const params = new URLSearchParams({
        client_id: process.env.GITHUB_CLIENT_ID!,
        redirect_uri: process.env.GITHUB_CALLBACK_URL!,
        // user:email   — read profile and email address
        // admin:repo_hook — create, update, and delete repository webhooks
        //   (write:repo_hook alone is insufficient for DELETE /hooks/:id)
        scope: "user:email admin:repo_hook",
    });
    return `https://github.com/login/oauth/authorize?${params.toString()}`;
};

export const getGithubAccessToken = async (code: string) => {
    const response = await axios.post(
        "https://github.com/login/oauth/access_token",
        {
            client_id: process.env.GITHUB_CLIENT_ID,
            client_secret: process.env.GITHUB_CLIENT_SECRET,
            code,
            redirect_uri: process.env.GITHUB_CALLBACK_URL,
        },
        {
            headers: {
                Accept: "application/json",
            },
        },
    );
    return response.data.access_token;
};

export const getGithubUser = async (accessToken: string) => {
    const response = await axios.get("https://api.github.com/user", {
        headers: {
            Authorization: `Bearer ${accessToken}`,
            Accept: "application/vnd.github+json",
        },
    });

    return response.data;
};

export const getGithubRepos = async (accessToken: string) => {
    const response = await axios.get("https://api.github.com/user/repos", {
        headers: {
            Authorization: `Bearer ${accessToken}`,
            Accept: "application/vnd.github+json",
        },
        params: {
            per_page: 100,
        },
    });

    return response.data.map((repo: any) => ({
        githubRepoId: repo.id,
        name: repo.name,
        owner: repo.owner.login,
        htmlUrl: repo.html_url,
        cloneUrl: repo.clone_url,
        defaultBranch: repo.default_branch,
        isPrivate: repo.private,
    }));
};

/**
 * Register an Autofix webhook on a GitHub repository.
 *
 * Requires the user's access token to have the `admin:repo_hook` scope.
 * The webhook is subscribed to `issues` and `workflow_run` events and uses
 * the server-side GITHUB_WEBHOOK_SECRET for HMAC-SHA256 verification.
 *
 * @returns The GitHub-assigned webhook ID (stored in repositories.github_webhook_id).
 */
export const createGithubWebhook = async (
    accessToken: string,
    owner: string,
    repo: string,
    webhookUrl: string,
    secret: string,
): Promise<{ id: number }> => {
    const response = await axios.post(
        `https://api.github.com/repos/${owner}/${repo}/hooks`,
        {
            name: "web",
            active: true,
            events: ["issues", "workflow_run"],
            config: {
                url: webhookUrl,
                content_type: "json",
                secret,
                insecure_ssl: "0",
            },
        },
        {
            headers: {
                Authorization: `Bearer ${accessToken}`,
                Accept: "application/vnd.github+json",
            },
        },
    );
    return { id: response.data.id };
};

/**
 * Delete an Autofix-managed webhook from a GitHub repository.
 *
 * Called when a user disconnects a repository from Autofix.
 * Errors are caught and logged by the caller (best-effort cleanup).
 */
export const deleteGithubWebhook = async (
    accessToken: string,
    owner: string,
    repo: string,
    webhookId: number,
): Promise<void> => {
    await axios.delete(
        `https://api.github.com/repos/${owner}/${repo}/hooks/${webhookId}`,
        {
            headers: {
                Authorization: `Bearer ${accessToken}`,
                Accept: "application/vnd.github+json",
            },
        },
    );
};

