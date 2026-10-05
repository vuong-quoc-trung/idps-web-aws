// ============================================================
// Student management types — mirrors backend DTOs
// ============================================================

export type Gender = 'MALE' | 'FEMALE' | 'OTHER';
export type StudentStatus = 'ACTIVE' | 'GRADUATED' | 'SUSPENDED' | 'INACTIVE';
export type AddressType = 'CURRENT' | 'PERMANENT' | 'FAMILY_HOME';
export type FamilyRelationship = 'MOTHER' | 'FATHER' | 'GUARDIAN' | 'OTHER';

// ---- Student summary (list view) — backend only returns IDs ----
export interface StudentSummary {
  id: number;
  studentCode: string;
  fullName: string;
  dateOfBirth?: string;
  gender?: Gender;
  status: StudentStatus;
  profileStatus?: string;
  classId?: number;
  majorId?: number;
  schoolEmail?: string;
  familyPhoneNumber?: string;
}

// ---- Student detail (GET /students/{id}) ----
export interface StudentDetail {
  birthCountryCode?: string;
  originCountryCode?: string;
  id: number;
  userId?: number;
  studentCode: string;
  fullName: string;
  dateOfBirth?: string;
  gender?: Gender;
  status: StudentStatus;
  profileStatus?: string;
  profileCompletedAt?: string;
  citizenId?: string;
  citizenIdIssueDate?: string;
  placeOfBirth?: string;
  oldPlaceOfBirth?: string;
  ethnicity?: string;
  nationality?: string;
  religion?: string;
  healthInsuranceNumber?: string;
  healthInsuranceExpiry?: string;
  freeHealthInsurance?: boolean;
  majorId?: number;
  classId?: number;
  trainingProgramId?: number;
  secondaryProgramId?: number;
  schoolEmail?: string;
  personalEmail?: string;
  phoneNumber?: string;
  familyPhoneNumber?: string;
  facebookUrl?: string;
  bankAccountNumber?: string;
  bankName?: string;
  avatarUrl?: string;
}

// ---- Profile completion ----
export interface CompletionStatus {
  status?: 'INCOMPLETE' | 'COMPLETE';
  complete?: boolean;
  percentage?: number;
  missingFields: string[];
  sections?: Record<string, boolean>;
}

// ---- Student self-update profile payload (/api/me/profile) ----
export interface UpdateStudentProfilePayload {
  birthCountryCode?: string;
  originCountryCode?: string;
  avatarUrl?: string | null;
  placeOfBirth?: string | null;
  oldPlaceOfBirth?: string | null;
  ethnicity?: string | null;
  nationality?: string | null;
  religion?: string | null;
  citizenIdIssueDate?: string | null;
  healthInsuranceNumber?: string | null;
  healthInsuranceExpiry?: string | null;
  freeHealthInsurance?: boolean;
  personalEmail?: string | null;
  phoneNumber?: string | null;
  facebookUrl?: string | null;
}

// ---- Create student payload ----
export interface CreateStudentPayload {
  fullName: string;
  dateOfBirth?: string;
  gender?: Gender;
  citizenId?: string;
  classId: number;
  secondaryProgramId?: number | null;
  familyPhoneNumber?: string;
}

// ---- Create student response ----
export interface CreateStudentResponse {
  student: StudentDetail;
  activationToken: string;
}

// ---- Update student payload ----
export interface UpdateStudentPayload {
  fullName: string;
  dateOfBirth?: string | null;
  gender?: Gender | null;
  citizenId?: string | null;
  classId: number;
  secondaryProgramId?: number | null;
  familyPhoneNumber?: string | null;
  bankAccountNumber?: string | null;
  bankName?: string | null;
  status: StudentStatus;
}

// ---- Address ----
export interface Address {
  countryCode?: string;
  id: number;
  addressType: AddressType;
  addressLine?: string;
  provinceCity?: string;
  wardCommune?: string;
  residenceRelation?: string;
  current: boolean;
}
export interface AddressPayload {
  countryCode?: string;
  addressType: AddressType;
  addressLine?: string;
  provinceCity?: string;
  wardCommune?: string;
  residenceRelation?: string;
  current: boolean;
}

// ---- Family member ----
export interface FamilyMember {
  id: number;
  relationship: FamilyRelationship;
  fullName?: string;
  dateOfBirth?: string;
  hasCollegeDegree: boolean;
  unavailable: boolean;
  phoneNumber?: string;
}
export interface FamilyMemberPayload {
  relationship: FamilyRelationship;
  fullName?: string;
  dateOfBirth?: string;
  hasCollegeDegree: boolean;
  unavailable: boolean;
  phoneNumber?: string;
}

// ---- Emergency contact ----
export interface EmergencyContact {
  id: number;
  fullName: string;
  relationship?: string;
  phoneNumber: string;
  address?: string;
  priority: number;
}
export interface EmergencyContactPayload {
  fullName: string;
  relationship?: string;
  phoneNumber: string;
  address?: string;
  priority: number;
}

// ---- Post-graduation contact ----
export interface PostGradContact {
  id: number;
  fullName?: string;
  phoneNumber?: string;
  email?: string;
  address?: string;
}
export interface PostGradContactPayload {
  fullName?: string;
  phoneNumber?: string;
  email?: string;
  address?: string;
}

// ---- Query params for student list ----
export interface StudentListParams {
  page?: number;
  size?: number;
  search?: string;
  majorId?: number | '';
  classId?: number | '';
  status?: StudentStatus | '';
}
