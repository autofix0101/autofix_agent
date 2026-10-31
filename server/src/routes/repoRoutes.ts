import { Router } from "express";
import { isLoggedIn } from "../middleware/auth.js";
import {
    createRepository,
    deleteRepo,
    fixSignal,
    getAllRepos,
    getRepoDetails,
    getRepoSignals,
    getSignalDetail,
    streamSignalProgress,
} from "../controllers/repositoryController.js";

const router = Router();

router.get("/", isLoggedIn, getAllRepos);
router.get("/:id", isLoggedIn, getRepoDetails);
router.get("/:id/signals", isLoggedIn, getRepoSignals);
router.get("/:id/signals/:signalId", isLoggedIn, getSignalDetail);
router.get("/:id/signals/:signalId/stream", isLoggedIn, streamSignalProgress);
router.post("/:id/signals/:signalId/fix", isLoggedIn, fixSignal);
router.post("/", isLoggedIn, createRepository);
router.delete("/:id", isLoggedIn, deleteRepo);

export default router;
