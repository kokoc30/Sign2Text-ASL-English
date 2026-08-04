"""Unit tests for AslOutputValidator and AslFallbackNormalizer.

Heavy ML imports (rtmlib, cv2, torch, numpy) are stubbed out so these tests
run without a GPU / ML environment installed.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


def _stub_heavy_imports():
    """Insert minimal stubs for ML packages not needed by the normalisation classes."""

    # ── torch ──────────────────────────────────────────────────────────────
    if "torch" not in sys.modules:
        # torch.nn.Module is needed as a base class for NN models in the file
        class _FakeModule:
            def __init__(self, *a, **kw): pass
            def __init_subclass__(cls, **kw): pass

        nn_mod = types.ModuleType("torch.nn")
        nn_mod.Module = _FakeModule
        nn_mod.Linear = _FakeModule
        nn_mod.GELU = _FakeModule
        nn_mod.LayerNorm = _FakeModule
        nn_mod.Dropout = _FakeModule
        nn_mod.functional = types.ModuleType("torch.nn.functional")

        mock_torch = types.ModuleType("torch")
        mock_torch.__version__ = "0.0.0"
        mock_torch.cuda = types.SimpleNamespace(
            is_available=lambda: False,
            get_device_name=lambda _i: None,
        )
        mock_torch.nn = nn_mod
        mock_torch.Tensor = object
        mock_torch.zeros = lambda *a, **kw: None
        mock_torch.float32 = "float32"
        mock_torch.no_grad = lambda: MagicMock(__enter__=lambda s, *a: None, __exit__=lambda s, *a: None)

        sys.modules["torch"] = mock_torch
        sys.modules["torch.nn"] = nn_mod
        sys.modules["torch.nn.functional"] = nn_mod.functional

    # ── numpy ──────────────────────────────────────────────────────────────
    if "numpy" not in sys.modules:
        mock_np = MagicMock()
        mock_np.ndarray = list
        mock_np.float32 = float
        sys.modules["numpy"] = mock_np

    # ── others ─────────────────────────────────────────────────────────────
    for name in ("rtmlib", "cv2"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()


_stub_heavy_imports()


def test_validator_rejects_overly_long_output(load_module):
    ni = load_module("new_Inference")
    validator = ni.AslOutputValidator(ni.NORM_CONFIG, ni.VALID_WORDS)

    # 2-token input → max allowed = 2 + 4 = 6 output words (hard cap 12)
    long_output = "The cat is very very very tall and happy and dancing."
    is_valid, reason = validator.validate("CAT TALL", long_output)
    assert not is_valid, f"Expected rejection but passed; reason would be: {reason}"


def test_validator_rejects_invented_content(load_module):
    ni = load_module("new_Inference")
    validator = ni.AslOutputValidator(ni.NORM_CONFIG, ni.VALID_WORDS)

    # "dancing" and "rooftop" are not in input tokens "CAT TALL"
    invented = "The cat is tall and dancing on the rooftop."
    is_valid, reason = validator.validate("CAT TALL", invented)
    assert not is_valid, f"Expected rejection for invented content; reason: {reason}"

    # Good output should pass
    is_valid, reason = validator.validate("CAT TALL", "The cat is tall.")
    assert is_valid, f"Expected valid output to pass; reason: {reason}"


def test_validator_preserves_question_form(load_module):
    ni = load_module("new_Inference")
    validator = ni.AslOutputValidator(ni.NORM_CONFIG, ni.VALID_WORDS)

    # Question sign present but output is not a question → rejected
    non_question = "How are you doing today."
    is_valid, reason = validator.validate("HOW YOU", non_question)
    assert not is_valid, f"Expected rejection for missing '?'; reason: {reason}"

    # Correct question form → accepted
    is_valid, reason = validator.validate("HOW YOU", "How are you?")
    assert is_valid, f"Expected 'How are you?' to pass; reason: {reason}"


def test_fallback_returns_short_safe_text(load_module):
    ni = load_module("new_Inference")
    fallback = ni.AslFallbackNormalizer()

    result = fallback.normalize(["ME", "HUNGRY"])
    assert result.startswith("I"), f"Expected ME→I mapping; got: {result!r}"
    assert result.endswith("."), f"Expected period at end; got: {result!r}"
    assert len(result) <= 20, f"Expected short output (≤20 chars); got: {result!r}"

    result_q = fallback.normalize(["HOW", "YOU"])
    assert result_q.endswith("?"), f"Expected question mark for HOW input; got: {result_q!r}"
