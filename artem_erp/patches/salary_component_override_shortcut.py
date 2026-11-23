from artem_erp.install import add_workspace_shortcut


def execute():
	add_workspace_shortcut(
		workspace_name="Payroll",
		label="Employees Salary Component Override",
		link_to="Employees Salary Component Override",
		icon="money-coins-1",
		link_type="DocType",
		item_type="Link",
		insert_after="Employee Additional Salary Payroll Review",
	)
