% AI-MBSE generated Simulink batch script
resultPath = 'E:/ai_mbse1/AI-MBSE-Demo/backend/exports/simulink/BLK-003_20260701_211204/simulink_result.json';
modelPath = '';
generatedModelPath = 'E:/ai_mbse1/AI-MBSE-Demo/backend/exports/simulink/BLK-003_20260701_211204/ai_mbse_BLK_003_20260701_211204.slx';
generatedModelName = 'ai_mbse_BLK_003_20260701_211204';
modelId = 'BLK-003';

try
    if exist('license', 'file') && ~license('test', 'Simulink')
        error('AI_MBSE:SimulinkUnavailable', 'Simulink license is not available.');
    end

    if ~isempty(modelPath)
        [modelDir, modelName, ~] = fileparts(modelPath);
        if ~isempty(modelDir)
            addpath(modelDir);
        end
        load_system(modelPath);
        simOut = sim(modelName, 'StopTime', '10');
        sourceModel = modelPath;
        try
            close_system(modelName, 0);
        catch
        end
    else
        modelName = generatedModelName;
        new_system(modelName);
        add_block('simulink/Sources/Step', [modelName '/Command'], 'Time', '1', 'Before', '0', 'After', '1');
        add_block('simulink/Continuous/Transfer Fcn', [modelName '/FirstOrderPlant'], 'Numerator', '[1]', 'Denominator', '[2 1]');
        add_block('simulink/Sinks/To Workspace', [modelName '/Response'], 'VariableName', 'ai_mbse_yout', 'SaveFormat', 'Array');
        add_line(modelName, 'Command/1', 'FirstOrderPlant/1');
        add_line(modelName, 'FirstOrderPlant/1', 'Response/1');
        set_param(modelName, 'StopTime', '10');
        save_system(modelName, generatedModelPath);
        simOut = sim(modelName, 'StopTime', '10');
        sourceModel = generatedModelPath;
        try
            close_system(modelName, 0);
        catch
        end
    end

    signal = [];
    if exist('ai_mbse_yout', 'var')
        signal = ai_mbse_yout;
    else
        try
            signal = simOut.get('ai_mbse_yout');
        catch
            signal = [];
        end
    end

    if isempty(signal)
        try
            logsout = simOut.logsout;
            if ~isempty(logsout) && logsout.numElements > 0
                ts = logsout.get(1).Values;
                signal = [ts.Time(:), ts.Data(:)];
            end
        catch
        end
    end

    if isnumeric(signal) && ~isempty(signal)
        if size(signal, 2) >= 2
            t = signal(:, 1);
            y = signal(:, 2);
        else
            y = signal(:);
            t = linspace(0, 10, numel(y))';
        end
    elseif isa(signal, 'timeseries')
        t = signal.Time(:);
        y = signal.Data(:);
    else
        try
            t = simOut.tout(:);
            y = zeros(size(t));
        catch
            t = [0; 10];
            y = [0; 0];
        end
    end

    y = y(:);
    t = t(:);
    finalValue = y(end);
    peakValue = max(y);
    duration = max(t) - min(t);
    denominator = max(abs(finalValue), eps);
    overshootPct = max(0, (peakValue - finalValue) / denominator * 100);
    band = max(0.02 * denominator, 1e-6);
    lastOutside = find(abs(y - finalValue) > band, 1, 'last');
    if isempty(lastOutside)
        settlingTime = 0;
    else
        settlingTime = t(min(lastOutside + 1, numel(t))) - min(t);
    end

    data = struct( ...
        'status', 'success', ...
        'model_id', modelId, ...
        'source_model_path', sourceModel, ...
        'simulated_duration_s', duration, ...
        'sample_count', numel(y), ...
        'final_value', finalValue, ...
        'peak_value', peakValue, ...
        'overshoot_pct', overshootPct, ...
        'settling_time_s', settlingTime ...
    );
    fid = fopen(resultPath, 'w');
    fwrite(fid, jsonencode(data), 'char');
    fclose(fid);
catch ME
    data = struct('status', 'error', 'message', ME.message, 'identifier', ME.identifier);
    fid = fopen(resultPath, 'w');
    fwrite(fid, jsonencode(data), 'char');
    fclose(fid);
    rethrow(ME);
end
