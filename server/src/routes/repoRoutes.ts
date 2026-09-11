import { Router } from "express";
import { isLoggedIn } from "../middleware/auth.js";
import {
    createRepository,
    deleteRepo,
    getAllRepos,
    getRepoDetails,
    getRepoSignals,
} from "../controllers/repositoryController.js";

const router = Router();

router.get("/", isLoggedIn, getAllRepos);
router.get("/:id", isLoggedIn, getRepoDetails);
router.get("/:id/signals", isLoggedIn, getRepoSignals);
router.post("/", isLoggedIn, createRepository);
router.delete("/:id", isLoggedIn, deleteRepo);

export default router;
