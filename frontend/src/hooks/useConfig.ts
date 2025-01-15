export const useConfig = () => {
  const isHostedEnvironment = import.meta.env.VITE_IS_HOSTED === 'true';
  const canUpdateValidators = !isHostedEnvironment;
  const canUpdateProviders = !isHostedEnvironment;
  const canUpdateFinalityWindow = !isHostedEnvironment;

  return {
    canUpdateValidators,
    canUpdateProviders,
    canUpdateFinalityWindow,
  };
};
