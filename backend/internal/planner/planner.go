package planner

// WorkflowPlanner decides which actions to execute and in what order
type WorkflowPlanner interface {
    Plan(entities ClaimEntities, intent Intent) (*WorkflowPlan, error)
}

type WorkflowPlan struct {
    Actions []ActionStep 
}

type ActionStep struct {
    Type       string   
    DependsOn  []string 
    Condition  string   
    Priority   int      
}

// Action types
const (
    ActionValidateData    = "validate_data"
    ActionGenerateReport  = "generate_report"
    ActionSendEmail       = "send_email"
    ActionMakeCall        = "make_call"
    ActionDispatchCar     = "dispatch_car"
    ActionEscalate        = "escalate"
)
