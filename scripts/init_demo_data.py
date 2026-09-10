from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

os.environ.setdefault("SYSML_ENABLE_REAL_API", "false")

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Requirement, SysMLElement, SysMLRelationship  # noqa: E402
from app.services.model_generation_service import ModelGenerationService  # noqa: E402
from app.services.requirement_service import RequirementService  # noqa: E402
from app.services.sysml_adapter import SysMLAdapter  # noqa: E402


DEMO_TEXT = """宽带通信系统应支持用户终端接入、链路资源管理、业务调度、网络状态监测和故障告警能力。
系统应支持对用户接入状态进行实时监测，并在链路质量下降时进行告警。
系统应支持根据业务优先级进行资源调度，并保障关键业务的传输质量。
系统应提供与外部网络管理系统的数据接口，用于状态同步和运维管理。
系统应支持对核心业务流程进行建模、追溯和变更影响分析。"""


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        db.query(SysMLRelationship).delete()
        db.query(SysMLElement).delete()
        db.query(Requirement).delete()
        db.commit()

        service = RequirementService(db)
        requirements = service.analyze_and_store(DEMO_TEXT, "宽带通信")
        for requirement in db.query(Requirement).all():
            requirement.status = "confirmed"
        db.commit()

        model = ModelGenerationService().generate(requirements)
        adapter = SysMLAdapter(db)
        for element in model["elements"]:
            adapter.create_element(element)
        for relationship in model["relationships"]:
            adapter.create_relationship(relationship)

        print("Demo data initialized.")
        print(f"Requirements: {len(requirements)}")
        print(f"Elements: {len(model['elements'])}")
        print(f"Relationships: {len(model['relationships'])}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
