from alembic import op
import sqlalchemy as sa

revision = "001_initial_schema"

down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generations_created_at"), "generations", ["created_at"])
    op.create_table(
        "dotfile_modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["generations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generation_id", "module_name", name="uq_generation_module"
        ),
    )
    op.create_index(
        op.f("ix_dotfile_modules_generation_id"),
        "dotfile_modules",
        ["generation_id"],
    )
    op.create_index(
        op.f("ix_dotfile_modules_module_name"),
        "dotfile_modules",
        ["module_name"],
    )
    op.create_table(
        "rendered_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("template_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["module_id"], ["dotfile_modules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id", "file_path", name="uq_module_file"),
    )
    op.create_index(
        op.f("ix_rendered_files_content_hash"),
        "rendered_files",
        ["content_hash"],
    )
    op.create_index(
        op.f("ix_rendered_files_module_id"),
        "rendered_files",
        ["module_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rendered_files_module_id"), table_name="rendered_files")
    op.drop_index(op.f("ix_rendered_files_content_hash"), table_name="rendered_files")
    op.drop_table("rendered_files")
    op.drop_index(op.f("ix_dotfile_modules_module_name"), table_name="dotfile_modules")
    op.drop_index(
        op.f("ix_dotfile_modules_generation_id"), table_name="dotfile_modules"
    )
    op.drop_table("dotfile_modules")
    op.drop_index(op.f("ix_generations_created_at"), table_name="generations")
    op.drop_table("generations")
