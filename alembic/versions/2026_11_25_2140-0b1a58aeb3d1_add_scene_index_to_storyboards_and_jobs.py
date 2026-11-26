"""add_scene_index_to_storyboards_and_jobs

Revision ID: 0b1a58aeb3d1
Revises: df8d8876064c
Create Date: 2026-11-25 21:40:15.441261+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b1a58aeb3d1'
down_revision: Union[str, Sequence[str], None] = 'df8d8876064c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) storyboards: 새 컬럼들 (scene_index는 일단 nullable로 추가)
    op.add_column("storyboards", sa.Column("scene_index", sa.Integer(), nullable=True))
    op.add_column("storyboards", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("storyboards", sa.Column("duration_sec", sa.Integer(), nullable=True))

    # 2) 기존 행 백필 — 전부 1번 장면으로 간주
    op.execute("UPDATE storyboards SET scene_index = 1 WHERE scene_index IS NULL")

    # 3) NOT NULL로 변경
    op.alter_column("storyboards", "scene_index", nullable=False)

    # 4) unique 제약 교체
    op.drop_constraint("uq_storyboards_video_id_revision", "storyboards", type_="unique")
    op.create_unique_constraint(
        "uq_storyboards_video_id_scene_index_revision",
        "storyboards",
        ["video_id", "scene_index", "revision"],
    )

    # 5) jobs: scene_index (nullable 유지)
    op.add_column("jobs", sa.Column("scene_index", sa.Integer(), nullable=True))

def downgrade() -> None:
    op.drop_column("jobs", "scene_index")
    op.drop_constraint("uq_storyboards_video_id_scene_index_revision", "storyboards", type_="unique")
    op.create_unique_constraint("uq_storyboards_video_id_revision", "storyboards", ["video_id", "revision"])
    op.drop_column("storyboards", "duration_sec")
    op.drop_column("storyboards", "description")
    op.drop_column("storyboards", "scene_index")
