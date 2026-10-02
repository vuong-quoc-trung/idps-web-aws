// ============================================================
// Academic catalog types — mirrors backend DTOs
// ============================================================

export type DegreeType = 'BACHELOR' | 'ENGINEER' | 'MASTER';

export interface Faculty {
  shortCode?: string;
  id: number;
  code: string;
  name: string;
  description?: string;
  active: boolean;
}

export interface Major {
  shortCode?: string;
  id: number;
  code: string;
  name: string;
  description?: string;
  active: boolean;
  facultyId: number;
  facultyName?: string;
}

export interface TrainingProgram {
  id: number;
  code: string;
  name: string;
  active: boolean;
  majorId: number;
  majorName?: string;
  cohort?: number;
  degreeType?: DegreeType | null;
  numberOfSemesters?: number | null;
  totalCredits?: number | null;
  requiredCredits?: number | null;
  electiveCredits?: number | null;
}

export interface StudentClass {
  id: number;
  code: string;
  name?: string;
  active: boolean;
  programId: number;
  programName?: string;
  cohort?: number;
  academicYear?: string;
}

// ---- Request payloads ----
export interface FacultyPayload {
  shortCode: string;
  name: string;
  description?: string;
  active: boolean;
}

export interface MajorPayload {
  shortCode: string;
  name: string;
  description?: string;
  active: boolean;
  facultyId: number;
}

export interface TrainingProgramPayload {
  name: string;
  active: boolean;
  majorId: number;
  cohort?: number | null;
  degreeType?: DegreeType | null;
  numberOfSemesters?: number | null;
  totalCredits?: number | null;
  requiredCredits?: number | null;
  electiveCredits?: number | null;
}

export interface StudentClassPayload {
  name?: string;
  active: boolean;
  programId: number;
  cohort?: number | null;
  academicYear?: string;
}
