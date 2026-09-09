ROLE_PERMISSIONS = {

    # ====== TRAVEL REQUEST ======

    "HR User": {
        "Travel Request": {
            "select": 1,
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
            "submit": 0,
            "cancel": 0,
            "amend": 1,
            "print": 0,
            "email": 0,
            "report": 0,
            "import": 1,
            "export": 1,
            "share": 0,
            "mask": 0,
        },
    },

    "HR Manager": {
        "Travel Request": {
            "select": 1,
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
            "submit": 1,
            "cancel": 1,
            "amend": 1,
            "print": 1,
            "email": 1,
            "report": 1,
            "import": 1,
            "export": 1,
            "share": 1,
            "mask": 0,
        },
    },
}