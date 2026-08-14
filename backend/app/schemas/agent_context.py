from pydantic import BaseModel


class MachineOverview(BaseModel):
    total: int
    reachable: int
    attention: int


class MemberOverview(BaseModel):
    active: int
    with_keys: int


class GrantOverview(BaseModel):
    active: int


class RunOverview(BaseModel):
    active: int
    failed_recently: int


class AgentOverview(BaseModel):
    machines: MachineOverview
    members: MemberOverview
    grants: GrantOverview
    runs: RunOverview
