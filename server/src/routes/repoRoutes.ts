import { Router } from "express";
import { isLoggedIn } from "../middleware/auth.js";
import {
    createRepository,
    deleteRepo,
    getAllRepos,
    getRepoDetails,
} from "../controllers/repositoryController.js";

const router = Router();

router.get("/", isLoggedIn, getAllRepos);
router.get("/:id", isLoggedIn, getRepoDetails);
router.post("/", isLoggedIn, createRepository);
router.delete("/", isLoggedIn, deleteRepo);

export default router;
