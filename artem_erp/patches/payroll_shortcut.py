from artem_erp.install import add_workspace_shortcut


def execute():
    add_workspace_shortcut(
        workspace_name="Payroll",
        label="Artem Employee CTC Breakup",
        link_to="Employee CTC Breakup",
        icon="file-chart-column",
        link_type="Report",
        item_type="Link",
        parent_label="Reports",
        child=1,
    )

    add_workspace_shortcut(
        workspace_name="Payroll",
        label="Employee Additional Salary Payroll Review",
        link_to="Employee Additional Salary Payroll Review",
        icon="file-check",
        link_type="DocType",
        item_type="Link",
        insert_after="Dashboard",
    )