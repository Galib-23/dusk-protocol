package xyz.brittoo.dusk;

import android.content.Context;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Tier-1 sensor bridge: streams hardware proximity near/far events AND
 * ambient-light lux readings to JS. The IR proximity sensor only covers
 * ~0-5 cm (often reported as binary near/far); the light sensor lets the
 * wave trigger see hand shadows from 7-15+ cm in normal lighting.
 */
@CapacitorPlugin(name = "Proximity")
public class ProximityPlugin extends Plugin implements SensorEventListener {

    private SensorManager sensorManager;
    private Sensor proximity;
    private Sensor light;
    private boolean watching = false;

    @Override
    public void load() {
        sensorManager = (SensorManager) getContext().getSystemService(Context.SENSOR_SERVICE);
        if (sensorManager != null) {
            proximity = sensorManager.getDefaultSensor(Sensor.TYPE_PROXIMITY);
            light = sensorManager.getDefaultSensor(Sensor.TYPE_LIGHT);
        }
    }

    @PluginMethod
    public void start(PluginCall call) {
        if (proximity == null && light == null) {
            call.reject("This device has neither proximity nor light sensor");
            return;
        }
        if (!watching) {
            if (proximity != null) {
                sensorManager.registerListener(this, proximity, SensorManager.SENSOR_DELAY_UI);
            }
            if (light != null) {
                sensorManager.registerListener(this, light, SensorManager.SENSOR_DELAY_UI);
            }
            watching = true;
        }
        JSObject info = new JSObject();
        info.put("hasProximity", proximity != null);
        info.put("hasLight", light != null);
        call.resolve(info);
    }

    @PluginMethod
    public void stop(PluginCall call) {
        if (watching) {
            sensorManager.unregisterListener(this);
            watching = false;
        }
        call.resolve();
    }

    @Override
    protected void handleOnDestroy() {
        if (watching) {
            sensorManager.unregisterListener(this);
            watching = false;
        }
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        JSObject data = new JSObject();
        if (event.sensor.getType() == Sensor.TYPE_PROXIMITY) {
            boolean near = event.values[0] < Math.min(proximity.getMaximumRange(), 5f);
            data.put("near", near);
            data.put("value", event.values[0]);
            notifyListeners("proximity", data);
        } else if (event.sensor.getType() == Sensor.TYPE_LIGHT) {
            data.put("lux", event.values[0]);
            notifyListeners("light", data);
        }
    }

    @Override
    public void onAccuracyChanged(Sensor s, int accuracy) {
    }
}
