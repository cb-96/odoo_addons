class PlannerOperationRollback(Exception):
    def __init__(self, result):
        super().__init__("Planner operation rolled back")
        self.result = result
