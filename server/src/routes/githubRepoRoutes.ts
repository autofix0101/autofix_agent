import { Router } from "express";
import { fetchGithubRepo } from "../controllers/githubRepoController.js";
import { isLoggedIn } from "../middleware/auth.js";

const router = Router();

router.get("/", isLoggedIn, fetchGithubRepo);

export default router;
