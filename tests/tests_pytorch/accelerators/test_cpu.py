import os
from pathlib import Path
from typing import Any, Dict, Union
from unittest.mock import Mock

import pytest
import torch

import pytorch_lightning as pl
from lightning_lite.plugins.io.torch_plugin import TorchCheckpointIO
from pytorch_lightning import Trainer
from pytorch_lightning.accelerators import CPUAccelerator
from pytorch_lightning.demos.boring_classes import BoringModel
from pytorch_lightning.plugins.precision.precision_plugin import PrecisionPlugin
from pytorch_lightning.strategies import SingleDeviceStrategy
from tests_pytorch.helpers.runif import RunIf


def test_restore_checkpoint_after_pre_setup_default():
    """Assert default for restore_checkpoint_after_setup is False."""
    plugin = SingleDeviceStrategy(
        accelerator=CPUAccelerator(), device=torch.device("cpu"), precision_plugin=PrecisionPlugin()
    )
    assert not plugin.restore_checkpoint_after_setup


def test_availability():
    assert CPUAccelerator.is_available()


@RunIf(psutil=True)
def test_get_device_stats(tmpdir):
    gpu_stats = CPUAccelerator().get_device_stats(Mock())
    fields = ["cpu_vm_percent", "cpu_percent", "cpu_swap_percent"]

    for f in fields:
        assert any(f in h for h in gpu_stats.keys())


@pytest.mark.parametrize("restore_after_pre_setup", [True, False])
def test_restore_checkpoint_after_pre_setup(tmpdir, restore_after_pre_setup):
    """Test to ensure that if restore_checkpoint_after_setup is True, then we only load the state after pre-
    dispatch is called."""

    class TestPlugin(SingleDeviceStrategy):
        setup_called = False

        def setup(self, trainer: "pl.Trainer") -> None:
            super().setup(trainer)
            self.setup_called = True

        @property
        def restore_checkpoint_after_setup(self) -> bool:
            return restore_after_pre_setup

        def load_checkpoint(self, checkpoint_path: Union[str, Path]) -> Dict[str, Any]:
            assert self.setup_called == restore_after_pre_setup
            return super().load_checkpoint(checkpoint_path)

    model = BoringModel()
    trainer = Trainer(default_root_dir=tmpdir, fast_dev_run=True)
    trainer.fit(model)

    checkpoint_path = os.path.join(tmpdir, "model.pt")
    trainer.save_checkpoint(checkpoint_path)

    plugin = TestPlugin(
        accelerator=CPUAccelerator(),
        precision_plugin=PrecisionPlugin(),
        device=torch.device("cpu"),
        checkpoint_io=TorchCheckpointIO(),
    )
    assert plugin.restore_checkpoint_after_setup == restore_after_pre_setup

    trainer = Trainer(default_root_dir=tmpdir, strategy=plugin, fast_dev_run=True)
    trainer.fit(model, ckpt_path=checkpoint_path)
    for func in (trainer.test, trainer.validate, trainer.predict):
        plugin.setup_called = False
        func(model, ckpt_path=checkpoint_path)
