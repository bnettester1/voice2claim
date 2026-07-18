package models

import (
	"time"
	"github.com/google/uuid"
	"gorm.io/datatypes"
)

type Claim struct {
	ID                  uuid.UUID      `gorm:"type:uuid;primaryKey" json:"id"`
	ClaimNumber         string         `gorm:"size:100;uniqueIndex" json:"claim_number"`
	ClaimTypeID         uuid.UUID      `json:"claim_type_id"`
	UserID              uuid.UUID      `json:"user_id"`
	IncidentDate        *time.Time     `json:"incident_date"`
	IncidentLocation    string         `json:"incident_location"`
	IncidentDescription string         `json:"incident_description"`
	Status              string         `gorm:"size:50;default:'pending'" json:"status"`
	Priority            string         `gorm:"size:20;default:'normal'" json:"priority"`
	EstimatedCost       float64        `json:"estimated_cost"`
	Currency            string         `gorm:"size:10;default:'VND'" json:"currency"`
	CreatedAt           time.Time      `json:"created_at"`
	UpdatedAt           time.Time      `json:"updated_at"`

	Vehicles []ClaimVehicle `gorm:"foreignKey:ClaimID" json:"vehicles"`
	Medical  *ClaimMedical  `gorm:"foreignKey:ClaimID" json:"medical"`
	Entities []ClaimEntity  `gorm:"foreignKey:ClaimID" json:"entities"`
}

type ClaimVehicle struct {
	ID                  uuid.UUID      `gorm:"type:uuid;primaryKey" json:"id"`
	ClaimID             uuid.UUID      `json:"claim_id"`
	VehicleModel        string         `json:"vehicle_model"`
	LicensePlate        string         `gorm:"size:20" json:"license_plate"`
	VehicleColor        string         `json:"vehicle_color"`
	VehicleYear         int            `json:"vehicle_year"`
	OwnerName           string         `json:"owner_name"`
	OwnerPhone          string         `json:"owner_phone"`
	Damages             datatypes.JSON `gorm:"type:jsonb" json:"damages"`
	DamageDescription   string         `json:"damage_description"`
	EstimatedRepairCost float64        `json:"estimated_repair_cost"`
	CreatedAt           time.Time      `json:"created_at"`
}

type ClaimMedical struct {
	ID                  uuid.UUID      `gorm:"type:uuid;primaryKey" json:"id"`
	ClaimID             uuid.UUID      `json:"claim_id"`
	PatientName         string         `json:"patient_name"`
	PatientIDCard       string         `json:"patient_id_card"`
	Diagnosis           string         `json:"diagnosis"`
	MedicalFacility     string         `json:"medical_facility"`
	Medications         datatypes.JSON `gorm:"type:jsonb" json:"medications"`
	CreatedAt           time.Time      `json:"created_at"`
}

type ClaimEntity struct {
	ID              uuid.UUID      `gorm:"type:uuid;primaryKey" json:"id"`
	ClaimID         uuid.UUID      `json:"claim_id"`
	EntityType      string         `gorm:"size:50" json:"entity_type"`
	Data            datatypes.JSON `gorm:"type:jsonb" json:"data"`
	ConfidenceScore float64        `json:"confidence_score"`
	SourceText      string         `json:"source_text"`
	CreatedAt       time.Time      `json:"created_at"`
}

type ClaimType struct {
	ID       uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	Code     string    `gorm:"size:50;uniqueIndex" json:"code"`
	NameVi   string    `gorm:"size:255" json:"name_vi"`
	IsActive bool      `gorm:"default:true" json:"is_active"`
}

type User struct {
	ID           uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	Email        string    `gorm:"size:255;uniqueIndex" json:"email"`
	FullName     string    `gorm:"size:255" json:"full_name"`
	Role         string    `gorm:"size:50;default:'adjuster'" json:"role"`
	IsActive     bool      `gorm:"default:true" json:"is_active"`
}