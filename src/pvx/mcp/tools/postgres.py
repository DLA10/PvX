from typing import Dict, Any, List
import sqlalchemy

class PostgresTool:
    """
    MCP tool for PostgreSQL operations.
    Implements security validation and result limits.
    """
    def __init__(self, connection_str: str, allowed_ops: List[str], blocked_ops: List[str], max_rows: int):
        self.connection_str = connection_str
        self.allowed_ops = allowed_ops
        self.blocked_ops = blocked_ops
        self.max_rows = max_rows
        self.engine = None

    def _get_engine(self):
        if not self.engine:
            self.engine = sqlalchemy.create_engine(self.connection_str)
        return self.engine

    def query(self, sql: str) -> Dict[str, Any]:
        sql_upper = sql.upper()
        if any(kw in sql_upper for kw in self.blocked_ops):
            return {"error": "SQL operation not allowed"}
            
        try:
            with self._get_engine().connect() as conn:
                result = conn.execute(sqlalchemy.text(sql))
                rows = [dict(r._mapping) for r in result.fetchmany(self.max_rows)]
                return {"rows": rows, "count": len(rows)}
        except Exception as e:
            return {"error": str(e)}
