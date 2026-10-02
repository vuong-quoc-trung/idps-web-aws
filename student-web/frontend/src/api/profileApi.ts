/**
 * profileApi - helpers for the authenticated STUDENT to read/write their own data.
 * Routes: GET /students (search by studentCode) -> /students/{id}/...
 * Pure frontend composition - no new backend endpoints needed.
 */
import { apiPut } from './client';
import { studentApi, addressApi, familyApi, emergencyApi, postGradApi } from './studentApi';
import type { StudentDetail, UpdateStudentPayload } from '../types/student';

/** Fields the student is allowed to update themselves */
export interface SelfUpdatePayload {
  personalEmail?: string | null;
  phoneNumber?: string | null;
  ethnicity?: string | null;
  religion?: string | null;
  healthInsuranceNumber?: string | null;
  healthInsuranceExpiry?: string | null;
  freeHealthInsurance?: boolean;
  facebookUrl?: string | null;
  bankAccountNumber?: string | null;
  bankName?: string | null;
}

/**
 * Fetch the student record for the current STUDENT user.
 * Strategy: search by studentCode (1:1 unique) -> grab first result -> full GET.
 */
export async function fetchMyStudent(studentCode: string): Promise<StudentDetail> {
  const page = await studentApi.list({ search: studentCode, size: 5 });
  const match = page.content.find(s => s.studentCode === studentCode);
  if (!match) throw new Error('Không tìm thấy hồ sơ sinh viên. Vui lòng liên hệ quản trị viên.');
  return studentApi.get(match.id);
}

/**
 * Update student-editable fields only.
 * Merges with immutable fields from current record and PUTs the full payload.
 */
export async function updateMyProfile(
  studentId: number,
  current: StudentDetail,
  patch: SelfUpdatePayload,
): Promise<StudentDetail> {
  const payload: UpdateStudentPayload = {
    fullName: current.fullName,
    dateOfBirth: current.dateOfBirth ?? null,
    gender: current.gender ?? null,
    citizenId: current.citizenId ?? null,
    classId: current.classId ?? 0,
    secondaryProgramId: current.secondaryProgramId ?? null,
    schoolEmail: current.schoolEmail ?? null,
    familyPhoneNumber: current.familyPhoneNumber ?? null,
    bankAccountNumber: patch.bankAccountNumber !== undefined
      ? patch.bankAccountNumber : (current.bankAccountNumber ?? null),
    bankName: patch.bankName !== undefined
      ? patch.bankName : (current.bankName ?? null),
    status: current.status,
  };
  return apiPut<StudentDetail>(`/students/${studentId}`, payload);
}

// Re-export sub-resource APIs for convenience
export { addressApi, familyApi, emergencyApi, postGradApi, studentApi };
