/**
 * Profile completion calculation helper.
 *
 * NOTE ON BACKEND LIMITATION:
 * The Spring Boot backend (`ProfileCompletionResult`) returns `{ status: ProfileStatus, missingFields: List<String> }`.
 * It does NOT return the authoritative total number of criteria or a pre-calculated percentage.
 *
 * As established in `StudentProfileCompletionService.java`, there are currently 17 discrete criteria evaluated:
 * 1. dateOfBirth
 * 2. gender
 * 3. placeOfBirth
 * 4. ethnicity
 * 5. nationality
 * 6. citizenId
 * 7. citizenIdIssueDate
 * 8. healthInsuranceNumber
 * 9. healthInsuranceExpiry
 * 10. trainingProgram
 * 11. personalEmail
 * 12. phoneNumber
 * 13. currentAddress (valid CURRENT address with isCurrent = true)
 * 14. permanentOrFamilyAddress (valid PERMANENT or FAMILY_HOME address with isCurrent = true)
 * 15. father (valid Father record or unavailable = true)
 * 16. mother (valid Mother record or unavailable = true)
 * 17. emergencyContact (valid emergency contact with priority > 0)
 */

export const TOTAL_PROFILE_CRITERIA = 17;

export interface CompletionCalculation {
  ready: boolean;
  isComplete: boolean;
  percent: number;
  missingCount: number;
  missingFields: string[];
}

export function calculateProfileCompletion(
  completion: { status?: string; complete?: boolean; missingFields?: string[] } | null | undefined
): CompletionCalculation {
  if (!completion) {
    return {
      ready: false,
      isComplete: false,
      percent: 0,
      missingCount: 0,
      missingFields: [],
    };
  }

  const missingFields = completion.missingFields ?? [];
  const missingCount = missingFields.length;
  const isComplete =
    completion.status === 'COMPLETE' ||
    completion.complete === true ||
    (completion.missingFields !== undefined && missingCount === 0);

  if (isComplete) {
    return {
      ready: true,
      isComplete: true,
      percent: 100,
      missingCount: 0,
      missingFields: [],
    };
  }

  // Calculate percentage bounded between 0 and 99 (100 is reserved only for fully complete)
  const completedCriteria = Math.max(0, TOTAL_PROFILE_CRITERIA - missingCount);
  const percent = Math.max(0, Math.min(99, Math.round((completedCriteria / TOTAL_PROFILE_CRITERIA) * 100)));

  return {
    ready: true,
    isComplete: false,
    percent,
    missingCount,
    missingFields,
  };
}
