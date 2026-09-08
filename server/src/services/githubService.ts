import axios from "axios";

export const getGithubAuthUrl = () => {
    const params = new URLSearchParams({
        client_id: process.env.GITHUB_CLIENT_ID!,
        redirect_uri: process.env.GITHUB_CALLBACK_URL!,
        scope: "user:email",
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
