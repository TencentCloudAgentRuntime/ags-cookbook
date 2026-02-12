"""
SWE-Bench RL Training with AGS — Standalone Script

Equivalent to running rllm_with_ags.ipynb (Steps 2–4).
Edit the configuration sections below before running:
  - AGS credentials (E2B_API_KEY, TENCENTCLOUD_SECRET_ID/KEY)
  - MODEL_PATH (local path to model weights)
  - MAX_SAMPLES (number of dataset examples per split)

Usage:
    python train.py
"""

import importlib
import os

# ============================================================
# User-configurable parameters
# ============================================================
MODEL_PATH = "/mnt/cfs-turbo/Qwen3-8B"
MAX_SAMPLES = 8  # per-split sample cap; set to None to use all data

SWE_DATASETS = [
    "R2E-Gym/SWE-Bench-Lite",   # 300 rows
    # "R2E-Gym/SWE-Bench-Verified",  # 500 rows
    "R2E-Gym/R2E-Gym-Subset",   # 4,578 rows
    # "R2E-Gym/R2E-Gym-Lite",   # 11,788 rows
    # "R2E-Gym/R2E-Gym-V1",     # 7.47k rows
    # "r2e-edits/SweSmith-RL-Dataset",
]


# ============================================================
# Step 1: Environment Variables
# ============================================================
env_config = {
    # -- AGS credentials (required: replace with your own values) --
    "E2B_API_KEY": "xxx",
    "TENCENTCLOUD_SECRET_ID": "xxx",
    "TENCENTCLOUD_SECRET_KEY": "xxx",
    "AGS_REGION": "ap-guangzhou",
    "TENCENTCLOUD_REGION": "ap-guangzhou",

    # -- HuggingFace mirror --
    "HF_ENDPOINT": "https://hf-mirror.com",

    # -- vLLM runtime --
    "VLLM_USE_V1": "1",
    "VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1",
    "VLLM_ENGINE_ITERATION_TIMEOUT_S": "1000000000",

    # -- PyTorch memory --
    "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:False",

    # -- MLflow monitoring (optional) --
    "MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING": "true",
    "MLFLOW_TRACKING_URI": "xxx",
    "MLFLOW_TRACKING_USERNAME": "xxx",
    "MLFLOW_TRACKING_PASSWORD": "xxx",
}


def setup_environment():
    """Apply environment variables."""
    os.environ.update(env_config)
    print("Environment variables configured.")


# ============================================================
# Step 2: Dataset Preparation
# ============================================================
def prepare_swe_data(max_samples: int | None = None):
    """
    Prepare and register SWE datasets for training and testing.

    Args:
        max_samples: If set, only use the first N examples per split.
                     Rows are sorted by docker_image (alphabetical) before slicing,
                     to match the ordering used by push_to_tcr.py.

    Returns:
        tuple: (train_datasets, test_datasets) - lists of registered datasets
    """
    from datasets import load_dataset

    from rllm.data.dataset import DatasetRegistry

    def make_process_fn():
        def process_fn(row):
            row_dict = dict(row)
            return row_dict
        return process_fn

    process_fn = make_process_fn()
    train_datasets = []
    test_datasets = []

    for dataset_name in SWE_DATASETS:
        print(f"Processing dataset: {dataset_name}")
        try:
            dataset_splits = load_dataset(dataset_name)
        except Exception as e:
            print(f"Failed to load dataset {dataset_name}: {e}")
            continue

        dataset_key = dataset_name.split("/")[-1].replace("-", "_")

        # Process train split if it exists
        if "train" in dataset_splits:
            print(f"Processing 'train' split for {dataset_name}")
            train_data = [process_fn(row) for row in dataset_splits["train"]]
            train_data.sort(key=lambda r: r.get("docker_image", ""))
            if max_samples is not None:
                train_data = train_data[:max_samples]
            train_dataset = DatasetRegistry.register_dataset(f"{dataset_key}", train_data, "train")
            train_datasets.append(train_dataset)
            print(f"Registered train dataset with {len(train_data)} examples")

        # Process test split if it exists
        if "test" in dataset_splits:
            print(f"Processing 'test' split for {dataset_name}")
            test_data = [process_fn(row) for row in dataset_splits["test"]]
            test_data.sort(key=lambda r: r.get("docker_image", ""))
            if max_samples is not None:
                test_data = test_data[:max_samples]
            test_dataset = DatasetRegistry.register_dataset(f"{dataset_key}", test_data, "test")
            test_datasets.append(test_dataset)
            print(f"Registered test dataset with {len(test_data)} examples")

        # If neither train nor test exists, use the first available split as train
        if "train" not in dataset_splits and "test" not in dataset_splits:
            available_splits = list(dataset_splits.keys())
            if available_splits:
                split_name = available_splits[0]
                print(f"Using '{split_name}' split as train data for {dataset_name}")
                train_data = [process_fn(row) for row in dataset_splits[split_name]]
                train_data.sort(key=lambda r: r.get("docker_image", ""))
                if max_samples is not None:
                    train_data = train_data[:max_samples]
                train_dataset = DatasetRegistry.register_dataset(f"{dataset_key}", train_data, "train")
                train_datasets.append(train_dataset)
                print(f"Registered train dataset with {len(train_data)} examples")

    return train_datasets, test_datasets


# ============================================================
# Step 3: Training
# ============================================================
def run_training(train_datasets, test_datasets):
    """Configure Hydra, build AgentTrainer, init Ray, and train."""
    import ray
    from hydra import compose, initialize_config_dir
    from hydra.core.global_hydra import GlobalHydra

    from rllm.agents.swe_agent import SWEAgent
    from rllm.environments.swe.swe import SWEEnv
    from rllm.trainer.agent_trainer import AgentTrainer
    from rllm.trainer.verl.ray_runtime_env import get_ppo_ray_runtime_env

    # Locate rllm's config directory
    rllm_pkg_dir = os.path.realpath(importlib.util.find_spec('rllm').submodule_search_locations[0])
    config_dir = os.path.join(rllm_pkg_dir, "rllm", "trainer", "config")

    # Clear any previous Hydra state
    GlobalHydra.instance().clear()

    with initialize_config_dir(config_dir=config_dir, version_base=None):
        config = compose(config_name="agent_ppo_trainer", overrides=[
            # Algorithm
            "algorithm.adv_estimator=rloo",
            "algorithm.kl_ctrl.kl_coef=0.001",
            # Data
            "data.train_batch_size=4",
            "data.val_batch_size=4",
            "data.max_prompt_length=4096",
            "data.max_response_length=32768",
            "data.filter_overlong_prompts=True",
            "data.filter_overlong_prompts_workers=32",
            # Actor / Rollout / Ref
            f"actor_rollout_ref.model.path={MODEL_PATH}",
            "actor_rollout_ref.hybrid_engine=True",
            "actor_rollout_ref.actor.optim.lr=1e-6",
            "actor_rollout_ref.model.use_remove_padding=True",
            "actor_rollout_ref.actor.loss_agg_mode=seq-mean-token-sum",
            "actor_rollout_ref.actor.ppo_mini_batch_size=8",
            "actor_rollout_ref.actor.use_dynamic_bsz=False",
            "actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=1",
            "actor_rollout_ref.rollout.log_prob_use_dynamic_bsz=True",
            "actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=1",
            "actor_rollout_ref.actor.ppo_max_token_len_per_gpu=40960",
            "actor_rollout_ref.actor.use_kl_loss=False",
            "actor_rollout_ref.actor.clip_ratio_high=0.28",
            "actor_rollout_ref.actor.kl_loss_coef=0.001",
            "actor_rollout_ref.actor.kl_loss_type=low_var_kl",
            "actor_rollout_ref.actor.ulysses_sequence_parallel_size=1",
            "actor_rollout_ref.model.enable_gradient_checkpointing=True",
            "actor_rollout_ref.actor.fsdp_config.param_offload=False",
            "actor_rollout_ref.actor.fsdp_config.optimizer_offload=False",
            "actor_rollout_ref.rollout.tensor_model_parallel_size=8",
            "actor_rollout_ref.rollout.name=vllm",
            "actor_rollout_ref.rollout.mode=async",
            "actor_rollout_ref.rollout.enforce_eager=False",
            "actor_rollout_ref.rollout.temperature=1.0",
            "actor_rollout_ref.rollout.gpu_memory_utilization=0.5",
            "actor_rollout_ref.rollout.n=4",
            "actor_rollout_ref.rollout.val_kwargs.n=1",
            "actor_rollout_ref.rollout.val_kwargs.temperature=0",
            "actor_rollout_ref.ref.fsdp_config.param_offload=False",
            "actor_rollout_ref.actor.entropy_coeff=0.0",
            # rllm
            "rllm.mask_truncated_samples=False",
            "rllm.filter_token_mismatch=False",
            "rllm.env.name=swe",
            "+rllm.env.env_args.backend=ags",
            "rllm.agent.name=sweagent",
            "rllm.agent.max_steps=50",
            "rllm.agent.overlong_filter=True",
            "+rllm.agent.trajectory_timeout=5400",
            # Trainer
            "trainer.critic_warmup=0",
            "trainer.logger=[console]",
            "trainer.project_name=AgentRL-with-ags",
            "trainer.experiment_name=swe-agent-rl",
            "trainer.val_before_train=False",
            "trainer.n_gpus_per_node=8",
            "trainer.nnodes=1",
            "trainer.save_freq=10",
            "trainer.test_freq=10",
            "trainer.default_hdfs_dir=null",
            "trainer.total_epochs=2",
        ])

    # train_datasets[0] = R2E_Gym_Subset, test_datasets[0] = SWE_Bench_Lite
    trainer = AgentTrainer(
        agent_class=SWEAgent,
        env_class=SWEEnv,
        config=config,
        train_dataset=train_datasets[0],
        val_dataset=test_datasets[0],
    )

    runtime_env = get_ppo_ray_runtime_env()
    runtime_env["env_vars"].update(env_config)

    if ray.is_initialized():
        ray.shutdown()
    ray.init(runtime_env=runtime_env)

    trainer.train()


# ============================================================
# Main
# ============================================================
def main():
    setup_environment()

    train_datasets, test_datasets = prepare_swe_data(max_samples=MAX_SAMPLES)
    print(f"\nDatasets ready: {len(train_datasets)} train, {len(test_datasets)} test")

    run_training(train_datasets, test_datasets)


if __name__ == "__main__":
    main()
