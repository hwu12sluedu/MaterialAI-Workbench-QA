from __future__ import annotations

import os
from pathlib import Path

import pytest


def _exercise_core_pages(page, base_url: str, evidence_name: str) -> None:
    evidence = Path.cwd() / "evidence" / "ui"
    evidence.mkdir(parents=True, exist_ok=True)
    page.goto(base_url, wait_until="domcontentloaded")
    page.get_by_text("系统诊断", exact=True).first.click()
    page.get_by_text("系统诊断", exact=True).last.wait_for()
    page.screenshot(path=evidence / f"{evidence_name}_diagnostics.png", full_page=True)
    page.get_by_text("带孔板验证", exact=True).first.click()
    page.get_by_text("三维带孔板验证", exact=True).wait_for()
    assert page.get_by_text("仅准备文件", exact=True).is_visible()
    assert page.get_by_text("确认允许创建并提交此 Abaqus Job", exact=True).is_visible()
    page.screenshot(path=evidence / f"{evidence_name}_plate_hole.png", full_page=True)

    page.get_by_text("案例库", exact=True).first.click()
    page.get_by_text("仅导出质量门合格案例", exact=True).wait_for()
    assert page.get_by_text("Abaqus 单位制", exact=True).is_visible()

    page.get_by_text("带孔板批量", exact=True).first.click()
    page.get_by_text("3D 带孔板批量仿真与代理模型", exact=True).wait_for()
    confirmation = page.get_by_text("确认允许本次提交 Abaqus Jobs", exact=True)
    if confirmation.count() == 0:
        page.get_by_role("button", name="创建批量计划", exact=True).click()
        confirmation.wait_for()
    assert confirmation.is_visible()
    assert page.get_by_role("button", name="运行真实求解", exact=True).is_disabled()
    page.screenshot(
        path=evidence / f"{evidence_name}_plate_hole_batch.png", full_page=True
    )


@pytest.mark.ui
def test_source_system_diagnostics_and_plate_hole_pages(page) -> None:
    if os.environ.get("MATERIALAI_QA_RUN_UI") != "1":
        pytest.skip("Set MATERIALAI_QA_RUN_UI=1 to run source UI checks.")
    base_url = os.environ.get("MATERIALAI_QA_APP_URL", "http://127.0.0.1:8501")
    _exercise_core_pages(page, base_url, "source")


@pytest.mark.ui
@pytest.mark.portable
def test_frozen_system_diagnostics_and_plate_hole_pages(
    page,
    frozen_app_url: str,
) -> None:
    if os.environ.get("MATERIALAI_QA_RUN_FROZEN_UI") != "1":
        pytest.skip("Set MATERIALAI_QA_RUN_FROZEN_UI=1 to run frozen UI checks.")
    _exercise_core_pages(page, frozen_app_url, "frozen")
