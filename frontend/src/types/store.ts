export interface ContractFile {
  id: string;
  name: string;
  content: string;
  example?: boolean;
  updatedAt?: string;
}

export interface OpenedFile {
  id: string;
  name: string;
}

export interface DeployedContract {
  contractId: string;
  address: string;
  defaultState: string;
}

export interface NodeLog {
  scope: string;
  name: string;
  type: 'error' | 'warning' | 'info' | 'success';
  message: string;
  data?: any;
}

export interface TransactionItem {
  hash: string;
  type: 'deploy' | 'method';
  status: string;
  contractAddress: string;
  localContractId: string;
  data?: any;
  decodedData?: {
    functionName: string;
    args: any[];
    kwargs: { [key: string]: any };
  };
}

export type UIMode = 'light' | 'dark';
export interface UIState {
  mode: UIMode;
  showTutorial: boolean;
}
