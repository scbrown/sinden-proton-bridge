// SindenBorder — BepInEx plugin that draws a white frame around the Unity
// game viewport so the Sinden Lightgun's camera-based tracker has a clear
// rectangle to lock onto.
//
// Hot-reloadable: writing to BepInEx/config/braino.sindenborder.cfg takes
// effect on the next frame; no game restart needed.

using System;
using System.IO;
using BepInEx;
using BepInEx.Configuration;
using UnityEngine;

namespace SindenBorder
{
    [BepInPlugin("braino.sindenborder", "Sinden Border Overlay", "0.2.0")]
    public class SindenBorderPlugin : BaseUnityPlugin
    {
        private ConfigEntry<int>   _borderWidth;
        private ConfigEntry<Color> _borderColor;
        private ConfigEntry<bool>  _enabled;

        private Texture2D _solidTex;
        private Color _cachedColor;

        private string _configPath;
        private DateTime _lastConfigMtime;
        private float _nextConfigCheck;

        void Awake()
        {
            _enabled     = Config.Bind("General", "Enabled",     true,
                "Draw the border overlay.");
            _borderWidth = Config.Bind("General", "BorderWidth", 60,
                "Border thickness in pixels (per side).");
            _borderColor = Config.Bind("General", "BorderColor", Color.white,
                "Border color (Sinden default matches RGB 255,255,255).");

            _solidTex = new Texture2D(1, 1, TextureFormat.RGBA32, false);
            ApplyColor();

            _configPath = Config.ConfigFilePath;
            try { _lastConfigMtime = File.GetLastWriteTime(_configPath); } catch {}

            Logger.LogMessage("SindenBorder loaded. width=" + _borderWidth.Value);
        }

        private void ApplyColor()
        {
            _cachedColor = _borderColor.Value;
            _solidTex.SetPixel(0, 0, _cachedColor);
            _solidTex.Apply();
        }

        void Update()
        {
            // Cheap hot-reload: every 0.5s, check the config file mtime;
            // if it changed, ask BepInEx to reload it.
            if (Time.unscaledTime < _nextConfigCheck) return;
            _nextConfigCheck = Time.unscaledTime + 0.5f;
            try
            {
                var t = File.GetLastWriteTime(_configPath);
                if (t > _lastConfigMtime)
                {
                    _lastConfigMtime = t;
                    Config.Reload();
                    ApplyColor();
                    Logger.LogMessage("SindenBorder config reloaded. width="
                                      + _borderWidth.Value);
                }
            }
            catch (Exception e)
            {
                Logger.LogWarning("Config reload check failed: " + e.Message);
            }
        }

        void OnGUI()
        {
            if (!_enabled.Value) return;
            if (_cachedColor != _borderColor.Value) ApplyColor();

            int w  = Screen.width;
            int h  = Screen.height;
            int bw = _borderWidth.Value;
            if (bw <= 0 || w <= 0 || h <= 0) return;

            GUI.DrawTexture(new Rect(0,      0,      w,  bw), _solidTex);
            GUI.DrawTexture(new Rect(0,      h - bw, w,  bw), _solidTex);
            GUI.DrawTexture(new Rect(0,      0,      bw, h ), _solidTex);
            GUI.DrawTexture(new Rect(w - bw, 0,      bw, h ), _solidTex);
        }
    }
}
