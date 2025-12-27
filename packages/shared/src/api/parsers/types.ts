/**
 * Parser Type Definitions
 */

import type { ApiResponse } from '../../types/api';

export type ListParser<TInput, TOutput = TInput> = (response: ApiResponse<TInput>) => TOutput[];

export type SingleParser<TInput, TOutput = TInput> = (
  response: ApiResponse<TInput>
) => TOutput | null;

export type CompositeParser<TOutput> = (response: ApiResponse) => TOutput;

export interface ParserOptions<TInput, TOutput = TInput> {
  resultSetIndex?: number;
  filter?: (item: TInput) => boolean;
  map?: (item: TInput) => TOutput;
  required?: boolean;
}
