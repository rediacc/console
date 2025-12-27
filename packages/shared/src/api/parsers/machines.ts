/**
 * Machine Parsers
 */

import { extractPrimaryOrSecondary, extractFirstByIndex } from './base';
import type { GetTeamMachines_ResultSet1 } from '../../types';
import type { ApiResponse } from '../../types/api';

export function parseGetTeamMachines(
  response: ApiResponse<GetTeamMachines_ResultSet1>
): GetTeamMachines_ResultSet1[] {
  return extractPrimaryOrSecondary(response).filter((machine) => Boolean(machine.machineName));
}

export function parseCreateMachine(
  response: ApiResponse<GetTeamMachines_ResultSet1>
): GetTeamMachines_ResultSet1 | null {
  return (
    extractFirstByIndex<GetTeamMachines_ResultSet1>(response, 1) ??
    extractFirstByIndex<GetTeamMachines_ResultSet1>(response, 0)
  );
}

export const parseMachineList = parseGetTeamMachines;
