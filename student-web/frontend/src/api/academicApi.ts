/**
 * Academic catalog API — CRUD for Faculties, Majors,
 * Training Programs, and Classes.
 */
import {
  apiGet, apiPost, apiPut, apiDelete,
  type Page,
} from './client';
import type {
  Faculty, FacultyPayload,
  Major, MajorPayload,
  TrainingProgram, TrainingProgramPayload,
  StudentClass, StudentClassPayload,
} from '../types/academic';

const PAGE_SIZE = 20;

// ============================================================
// Faculties
// ============================================================
export const facultyApi = {
  list: (page = 0) =>
    apiGet<Page<Faculty>>('/faculties', { page, size: PAGE_SIZE }),
  listAll: () =>
    apiGet<Page<Faculty>>('/faculties', { page: 0, size: 200 }),
  get: (id: number) =>
    apiGet<Faculty>(`/faculties/${id}`),
  create: (payload: FacultyPayload) =>
    apiPost<Faculty>('/faculties', payload),
  update: (id: number, payload: FacultyPayload) =>
    apiPut<Faculty>(`/faculties/${id}`, payload),
  remove: (id: number) =>
    apiDelete(`/faculties/${id}`),
};

// ============================================================
// Majors
// ============================================================
export const majorApi = {
  list: (page = 0) =>
    apiGet<Page<Major>>('/majors', { page, size: PAGE_SIZE }),
  listAll: () =>
    apiGet<Page<Major>>('/majors', { page: 0, size: 500 }),
  get: (id: number) =>
    apiGet<Major>(`/majors/${id}`),
  create: (payload: MajorPayload) =>
    apiPost<Major>('/majors', payload),
  update: (id: number, payload: MajorPayload) =>
    apiPut<Major>(`/majors/${id}`, payload),
  remove: (id: number) =>
    apiDelete(`/majors/${id}`),
};

// ============================================================
// Training Programs
// ============================================================
export const programApi = {
  list: (page = 0) =>
    apiGet<Page<TrainingProgram>>('/training-programs', { page, size: PAGE_SIZE }),
  listAll: () =>
    apiGet<Page<TrainingProgram>>('/training-programs', { page: 0, size: 500 }),
  get: (id: number) =>
    apiGet<TrainingProgram>(`/training-programs/${id}`),
  create: (payload: TrainingProgramPayload) =>
    apiPost<TrainingProgram>('/training-programs', payload),
  update: (id: number, payload: TrainingProgramPayload) =>
    apiPut<TrainingProgram>(`/training-programs/${id}`, payload),
  remove: (id: number) =>
    apiDelete(`/training-programs/${id}`),
};

// ============================================================
// Classes
// ============================================================
export const classApi = {
  list: (page = 0) =>
    apiGet<Page<StudentClass>>('/classes', { page, size: PAGE_SIZE }),
  listAll: () =>
    apiGet<Page<StudentClass>>('/classes', { page: 0, size: 500 }),
  get: (id: number) =>
    apiGet<StudentClass>(`/classes/${id}`),
  create: (payload: StudentClassPayload) =>
    apiPost<StudentClass>('/classes', payload),
  update: (id: number, payload: StudentClassPayload) =>
    apiPut<StudentClass>(`/classes/${id}`, payload),
  remove: (id: number) =>
    apiDelete(`/classes/${id}`),
};
