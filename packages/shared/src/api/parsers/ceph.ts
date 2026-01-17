/**
 * Ceph Parsers
 */

import { extractFirstByIndex, extractRowsByIndex } from './base';
import type {
  CephAvailableMachine,
  CephCloneMachine,
  CephMachineAssignmentStatus,
  CephMachineAssignmentValidation,
  GetCephClusterMachines_ResultSet1,
  GetCephClusters_ResultSet1,
  GetCephPools_ResultSet1,
  GetCephRbdClones_ResultSet1,
  GetCephRbdImages_ResultSet1,
  GetCephRbdSnapshots_ResultSet1,
} from '../../types';
import type { ApiResponse } from '../../types/api';

export function parseGetCephClusters(
  response: ApiResponse<GetCephClusters_ResultSet1>
): GetCephClusters_ResultSet1[] {
  return extractRowsByIndex<GetCephClusters_ResultSet1>(response, 1);
}

export function parseGetCephClusterMachines(
  response: ApiResponse<GetCephClusterMachines_ResultSet1>
): GetCephClusterMachines_ResultSet1[] {
  return extractRowsByIndex<GetCephClusterMachines_ResultSet1>(response, 1);
}

export function parseGetCephPools(
  response: ApiResponse<GetCephPools_ResultSet1>
): GetCephPools_ResultSet1[] {
  return extractRowsByIndex<GetCephPools_ResultSet1>(response, 1);
}

export function parseGetCephRbdImages(
  response: ApiResponse<GetCephRbdImages_ResultSet1>
): GetCephRbdImages_ResultSet1[] {
  return extractRowsByIndex<GetCephRbdImages_ResultSet1>(response, 1);
}

export function parseGetCephRbdSnapshots(
  response: ApiResponse<GetCephRbdSnapshots_ResultSet1>
): GetCephRbdSnapshots_ResultSet1[] {
  return extractRowsByIndex<GetCephRbdSnapshots_ResultSet1>(response, 1);
}

export function parseGetCephRbdClones(
  response: ApiResponse<GetCephRbdClones_ResultSet1>
): GetCephRbdClones_ResultSet1[] {
  return extractRowsByIndex<GetCephRbdClones_ResultSet1>(response, 1);
}

export function parseGetMachineAssignmentStatus(
  response: ApiResponse<CephMachineAssignmentStatus>
): CephMachineAssignmentStatus | null {
  return extractFirstByIndex<CephMachineAssignmentStatus>(response, 0);
}

export function parseGetAvailableMachinesForClone(
  response: ApiResponse<CephAvailableMachine>
): CephAvailableMachine[] {
  return extractRowsByIndex<CephAvailableMachine>(response, 0);
}

export function parseGetCloneMachineAssignmentValidation(
  response: ApiResponse<CephMachineAssignmentValidation>
): CephMachineAssignmentValidation[] {
  return extractRowsByIndex<CephMachineAssignmentValidation>(response, 0);
}

export function parseGetCloneMachines(response: ApiResponse<CephCloneMachine>): CephCloneMachine[] {
  return extractRowsByIndex<CephCloneMachine>(response, 0);
}

export const parseClusters = parseGetCephClusters;
export const parsePools = parseGetCephPools;
export const parseImages = parseGetCephRbdImages;
export const parseSnapshots = parseGetCephRbdSnapshots;
export const parseClones = parseGetCephRbdClones;
