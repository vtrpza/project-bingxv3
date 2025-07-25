"""
Main PyScript Application for BingX Trading Bot Dashboard
Coordinates all frontend functionality and real-time updates
"""

import asyncio
import json
from datetime import datetime, timedelta
try:
    from js import document, console, setInterval, clearInterval, setTimeout, window
    import js
except ImportError:
    # Fallback for testing or other environments
    js = None
    document = None
    console = None
    setInterval = None
    clearInterval = None
    setTimeout = None
    window = None
from pyodide.ffi import create_proxy

# Import our modules
from api_client import api_client
from components import ui_components


class TradingBotApp:
    def __init__(self):
        self.update_interval = None
        self.auto_refresh_enabled = True
        self.refresh_rate = 10000  # 10 seconds (reduzido para evitar concorrência)
        self.current_tab = "scanner"
        
        # Cache para evitar atualizações desnecessárias
        self.last_validation_data = None
        self.last_validation_timestamp = None
        self.update_in_progress = False
        
        # Client-side operation mode - DISABLED
        self.scanning_active = False  # Force disable client-side mode
        self.client_side_cache = None  # Cache disabled
        self.current_search_term = ""
        self.current_filters = {}
        self.current_sort = {'column': 'symbol', 'direction': 'asc'}
        
        # Initialize after DOM is ready
        self.initialize()
    
    def initialize(self):
        """Initialize the application"""
        console.log("Initializing BingX Trading Bot Dashboard...")
        
        # Connect to WebSocket
        api_client.connect_websocket()
        
        # Set up WebSocket event handlers
        api_client.on_message("realtime_update", create_proxy(self.handle_realtime_update))
        api_client.on_message("pong", create_proxy(self.handle_pong))
        
        # Load initial data
        asyncio.create_task(self.load_initial_data())
        
        # Set up auto-refresh
        self.setup_auto_refresh()
        
        # Set up event listeners
        self.setup_event_listeners()
        
        console.log("Dashboard initialized successfully")
    
    async def load_initial_data(self):
        """Load initial dashboard data with proper progress tracking"""
        loading_overlay = document.getElementById("loading-overlay")
        progress_bar = document.getElementById("progress-bar")
        progress_percentage = document.getElementById("progress-percentage")
        progress_subtitle = document.getElementById("progress-subtitle")
        
        loading_overlay.style.display = "flex"
        
        # Initialize progress tracking
        total_steps = 5
        current_step = 0
        
        def update_progress(step, message):
            nonlocal current_step
            current_step = step
            progress = (current_step / total_steps) * 100
            progress_bar.style.width = f"{progress}%"
            progress_percentage.textContent = f"{progress:.0f}%"
            progress_subtitle.textContent = message
            console.log(f"Loading progress: {progress:.0f}% - {message}")
        
        # Set maximum loading time of 15 seconds
        loading_timeout = None
        try:
            if js:
                loading_timeout = js.setTimeout(js.Function.fromString("() => { window.forceHideLoading(); }"), 15000)
        except:
            # Fallback if setTimeout not available
            if console:
                console.warn("setTimeout not available, using manual timeout")
        
        try:
            # Step 1: Dashboard summary (critical)
            update_progress(1, "Carregando resumo do dashboard...")
            try:
                await self.update_dashboard_summary()
                console.log("✅ Dashboard summary loaded")
            except Exception as e:
                console.error(f"❌ Dashboard summary failed: {e}")
            
            # Step 2: Validation table (critical)
            update_progress(2, "Carregando tabela de validação...")
            try:
                await self.update_validation_table()
                console.log("✅ Validation table loaded")
            except Exception as e:
                console.error(f"❌ Validation table failed: {e}")
            
            # Step 3: Scanner data (non-critical)
            update_progress(3, "Carregando dados do scanner...")
            try:
                await self.update_scanner_data()
                console.log("✅ Scanner data loaded")
            except Exception as e:
                console.error(f"⚠️ Scanner data failed: {e}")
            
            # Step 4: Trading data (non-critical)
            update_progress(4, "Carregando dados de trading...")
            try:
                await self.update_trading_data()
                console.log("✅ Trading data loaded")
            except Exception as e:
                console.error(f"⚠️ Trading data failed: {e}")
            
            # Step 5: Positions data (non-critical)
            update_progress(5, "Finalizando carregamento...")
            try:
                await self.update_positions_data()
                console.log("✅ Positions data loaded")
            except Exception as e:
                console.error(f"⚠️ Positions data failed: {e}")
            
            # Complete loading
            update_progress(5, "Dados carregados com sucesso!")
            ui_components.show_notification(
                "Dashboard", 
                "Sistema inicializado com sucesso", 
                "success"
            )
            
        except Exception as e:
            console.error(f"Critical error loading initial data: {str(e)}")
            progress_subtitle.textContent = "Erro ao carregar dados"
            ui_components.show_notification(
                "Erro", 
                "Falha crítica ao carregar dados", 
                "error"
            )
        finally:
            # Clear timeout and hide loading after a short delay to show completion
            if loading_timeout and js:
                try:
                    js.clearTimeout(loading_timeout)
                except:
                    pass
            
            # Show completion for 1 second before hiding
            try:
                if js:
                    js.setTimeout(js.Function.fromString("() => { document.getElementById('loading-overlay').style.display = 'none'; }"), 1000)
                else:
                    loading_overlay.style.display = "none"
            except:
                loading_overlay.style.display = "none"
            
            console.log("Loading completed - overlay will hide shortly")
    
    def _force_hide_loading(self):
        """Force hide loading overlay after timeout"""
        document.getElementById("loading-overlay").style.display = "none"
        ui_components.show_notification(
            "Timeout", 
            "Carregamento demorou mais que esperado", 
            "warning"
        )
        console.warn("⏰ Loading timeout reached - forcing hide")
    
    async def check_scanning_status(self):
        """Check if scanning is currently active - DISABLED: Always use server-side mode"""
        try:
            # Force disable client-side scanning mode
            old_status = self.scanning_active
            self.scanning_active = False
            
            # Se estava em client-side, limpar cache e voltar ao server-side
            if old_status:
                console.log("⏹️  Client-side scanning disabled - reverting to server-side table operations")
                self.clear_client_side_cache()
                
            return False
        except Exception as e:
            console.log(f"Scanner status check disabled (using server-side mode): {e}")
            self.scanning_active = False
            self.clear_client_side_cache()
            return False

    async def load_full_data_for_client_side(self):
        """Load complete data set for client-side operations during scanning"""
        try:
            console.log("Loading complete dataset for client-side operations...")
            
            # Obter todos os dados sem paginação
            full_data = await api_client.get_validation_table(
                page=1,
                per_page=1000,  # Valor alto para pegar todos
                include_invalid=True
            )
            
            if full_data:
                self.client_side_cache = full_data
                console.log(f"Loaded {len(full_data.get('table_data', []))} records for client-side operations")
                
                # Atualizar UI para mostrar que está em modo client-side
                self.show_client_side_mode_indicator(True)
                ui_components.show_notification(
                    "Modo Scanning", 
                    "Tabela otimizada para scanning ativo - operações locais habilitadas", 
                    "info"
                )
                
        except Exception as e:
            console.error(f"Error loading full data: {e}")

    def clear_client_side_cache(self):
        """Clear client-side cache and revert to server-side operations"""
        self.client_side_cache = None
        self.current_search_term = ""
        self.current_filters = {}
        self.current_sort = {'column': 'symbol', 'direction': 'asc'}
        
        self.show_client_side_mode_indicator(False)
        ui_components.show_notification(
            "Modo Server-side", 
            "Scanning parado - voltou para operações server-side", 
            "info"
        )

    def show_client_side_mode_indicator(self, show):
        """Show/hide the client-side mode indicator - ALWAYS HIDDEN"""
        try:
            indicator = document.getElementById("table-mode-indicator")
            if indicator:
                indicator.style.display = "none"  # Always hidden
        except Exception as e:
            console.error(f"Error updating mode indicator: {e}")

    async def update_dashboard_summary(self):
        """Update dashboard summary statistics"""
        try:
            # Check scanning status first
            await self.check_scanning_status()
            
            summary_data = await api_client.get_dashboard_summary()
            if summary_data:
                ui_components.update_stats_cards(summary_data)
        except Exception as e:
            console.error(f"Error updating dashboard summary: {str(e)}")
    
    async def update_validation_table(self, page=1):
        """Update asset validation table - ALWAYS use server-side logic"""
        # Evita atualizações simultâneas
        if self.update_in_progress:
            console.log("Validation table update already in progress, skipping...")
            return
            
        try:
            self.update_in_progress = True
            
            # Always use server-side mode (client-side disabled)
            console.log(f"Using server-side table update - page {page}")
            
            # Get validation table data with pagination
            validation_data = await api_client.get_validation_table(
                page=page,
                per_page=25,
                include_invalid=True
            )
            
            if validation_data:
                # Verificar se os dados realmente mudaram
                current_timestamp = validation_data.get("summary", {}).get("last_updated")
                
                if (self.last_validation_data is not None and 
                    self.last_validation_timestamp == current_timestamp and
                    page == 1):  # Only skip if same page and timestamp
                    console.log("Validation data unchanged, skipping UI update")
                    return
                
                # Atualizar cache
                self.last_validation_data = validation_data
                self.last_validation_timestamp = current_timestamp
                
                # Atualizar UI
                ui_components.update_validation_table(validation_data)
                
                # Update summary stats
                summary = validation_data.get("summary", {})
                pagination = validation_data.get("pagination", {})
                self.update_validation_stats(summary)
                
                console.log(f"Validation table updated - Page {pagination.get('current_page', 1)}/{pagination.get('total_pages', 1)}, Total: {summary.get('total_assets', 0)}")
                
        except Exception as e:
            console.error(f"Error updating validation table: {str(e)}")
        finally:
            self.update_in_progress = False

    async def update_table_client_side(self):
        """Update table using client-side cached data"""
        try:
            if not self.client_side_cache:
                console.log("No client-side cache available")
                return
                
            # Aplicar filtros, busca e ordenação no cache
            filtered_data = self.apply_client_side_operations(self.client_side_cache)
            
            # Atualizar UI com dados filtrados
            ui_components.update_validation_table(filtered_data)
            
            console.log(f"Client-side table updated - {len(filtered_data.get('table_data', []))} records displayed")
            
        except Exception as e:
            console.error(f"Error in client-side table update: {e}")

    def apply_client_side_operations(self, data):
        """Apply search, filters, and sorting to cached data"""
        try:
            table_data = data.get("table_data", [])
            
            # 1. Aplicar busca
            if self.current_search_term:
                filtered_data = []
                search_lower = self.current_search_term.lower()
                for item in table_data:
                    symbol = item.get("symbol", "").lower()
                    if search_lower in symbol:
                        filtered_data.append(item)
                table_data = filtered_data
            
            # 2. Aplicar filtros
            if self.current_filters:
                if self.current_filters.get("filter_valid_only"):
                    table_data = [item for item in table_data if item.get("validation_status") == "VALID"]
                
                if self.current_filters.get("priority_only"):
                    table_data = [item for item in table_data if item.get("priority_asset")]
                    
                if self.current_filters.get("trading_enabled_only"):
                    table_data = [item for item in table_data if item.get("trading_enabled")]
                    
                risk_filter = self.current_filters.get("risk_level_filter")
                if risk_filter and risk_filter != "all":
                    table_data = [item for item in table_data if item.get("risk_level") == risk_filter.upper()]
            
            # 3. Aplicar ordenação
            if self.current_sort and self.current_sort.get("column"):
                column = self.current_sort["column"]
                reverse = self.current_sort["direction"] == "desc"
                
                def get_sort_key(item):
                    value = item.get(column)
                    if value is None:
                        return ""
                    # Para colunas numéricas
                    if column in ["validation_score", "current_price", "volume_24h_quote", "spread_percent", "data_quality_score", "age_days"]:
                        try:
                            return float(value)
                        except (ValueError, TypeError):
                            return 0
                    # Para texto
                    return str(value).lower()
                
                table_data.sort(key=get_sort_key, reverse=reverse)
            
            # Criar estrutura de retorno simulando paginação
            return {
                "table_data": table_data,
                "summary": data.get("summary", {}),
                "pagination": {
                    "current_page": 1,
                    "total_pages": 1,
                    "total_records": len(table_data),
                    "showing_records": len(table_data)
                }
            }
            
        except Exception as e:
            console.error(f"Error applying client-side operations: {e}")
            return data
    
    async def search_and_update_table(self, search_term="", page=1):
        """Search and update validation table - ALWAYS use server-side logic"""
        try:
            console.log(f"Performing search for: '{search_term}' on page {page}")
            
            # Atualizar termo de busca atual
            self.current_search_term = search_term
            
            # Always use server-side search
            console.log("Using server-side search")
            
            # Get search results from API with pagination
            validation_data = await api_client.get_validation_table(
                page=page,
                per_page=25,
                include_invalid=True,
                search=search_term if search_term else None
            )
            
            if validation_data:
                ui_components.update_validation_table(validation_data)
            
            # Update search indicator
            search_input = document.getElementById("symbol-search")
            if search_input:
                if search_term:
                    search_input.style.backgroundColor = "#e8f4fd"
                    search_input.style.borderColor = "#0969da"
                else:
                    search_input.style.backgroundColor = ""
                    search_input.style.borderColor = ""
                        
        except Exception as e:
            console.error(f"Error during search: {str(e)}")
    
    async def sort_validation_table_server(self, column, direction):
        """Sort validation table with adaptive client/server-side logic"""
        try:
            console.log(f"Sorting: {column} {direction}")
            
            # Atualizar ordenação atual
            self.current_sort = {'column': column, 'direction': direction}
            
            # Se scanning ativo e temos cache, usar client-side
            if self.scanning_active and self.client_side_cache:
                console.log("Using client-side sorting (scanning active)")
                await self.update_table_client_side()
            else:
                # Usar server-side normal
                console.log("Using server-side sorting")
                
                # Get current search term
                search_input = document.getElementById("symbol-search")
                search_term = search_input.value.strip() if search_input else ""
                
                # Get sorted data from API
                validation_data = await api_client.get_validation_table(
                    page=1,  # Reset to first page on sort
                    per_page=25,
                    sort_by=column,
                    sort_direction=direction,
                    include_invalid=True,
                    search=search_term if search_term else None
                )
                
                if validation_data:
                    ui_components.update_validation_table(validation_data)
                
        except Exception as e:
            console.error(f"Error sorting table: {str(e)}")
    
    async def refresh_validation_table_page(self, page):
        """Refresh validation table for specific page"""
        try:
            console.log(f"Refreshing validation table page {page}")
            
            # Get current search and sort
            search_input = document.getElementById("symbol-search")
            search_term = search_input.value.strip() if search_input else ""
            
            current_sort = getattr(ui_components, '_current_sort', {'column': 'symbol', 'direction': 'asc'})
            
            # Get page data from API
            validation_data = await api_client.get_validation_table(
                page=page,
                per_page=25,
                sort_by=current_sort.get('column', 'symbol'),
                sort_direction=current_sort.get('direction', 'asc'),
                include_invalid=True,
                search=search_term if search_term else None
            )
            
            if validation_data:
                ui_components.update_validation_table(validation_data)
                
        except Exception as e:
            console.error(f"Error refreshing page: {str(e)}")
    
    async def apply_validation_table_filters(self, filters):
        """Apply filters to validation table with adaptive client/server-side logic"""
        try:
            console.log(f"Applying filters: {filters}")
            
            # Atualizar filtros atuais
            self.current_filters = filters
            
            # Se scanning ativo e temos cache, usar client-side
            if self.scanning_active and self.client_side_cache:
                console.log("Using client-side filtering (scanning active)")
                await self.update_table_client_side()
            else:
                # Usar server-side normal
                console.log("Using server-side filtering")
                
                # Get current search and sort
                search_input = document.getElementById("symbol-search")
                search_term = search_input.value.strip() if search_input else ""
                
                current_sort = getattr(ui_components, '_current_sort', {'column': 'symbol', 'direction': 'asc'})
                
                # Get filtered data from API
                validation_data = await api_client.get_validation_table(
                    page=1,  # Reset to first page on filter
                    per_page=25,
                    sort_by=current_sort.get('column', 'symbol'),
                    sort_direction=current_sort.get('direction', 'asc'),
                    filter_valid_only=filters.get('filter_valid_only', False),
                    include_invalid=not filters.get('filter_valid_only', False),
                    search=search_term if search_term else None,
                    risk_level_filter=filters.get('risk_level_filter'),
                    priority_only=filters.get('priority_only', False),
                    trading_enabled_only=filters.get('trading_enabled_only', False)
                )
                
                if validation_data:
                    ui_components.update_validation_table(validation_data)
                
        except Exception as e:
            console.error(f"Error applying filters: {str(e)}")
    
    def update_validation_stats(self, summary):
        """Update validation statistics in the UI"""
        try:
            # Update stats cards
            elements = {
                "total-symbols-count": summary.get("total_assets", 0),
                "valid-assets-count": summary.get("valid_assets", 0),
                "assets-with-signals-count": summary.get("assets_with_signals", 0)
            }
            
            for element_id, value in elements.items():
                element = document.getElementById(element_id)
                if element:
                    element.textContent = str(value)
                    
            # Update last update time
            last_update = summary.get("last_updated")
            if last_update:
                update_element = document.getElementById("last-update")
                if update_element:
                    # Parse ISO timestamp and format to UTC-3
                    try:
                        dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                        # Convert to UTC-3
                        dt_utc3 = dt - timedelta(hours=3)
                        update_element.textContent = dt_utc3.strftime("%H:%M:%S (UTC-3)")
                    except:
                        update_element.textContent = "Agora"
                        
        except Exception as e:
            console.error(f"Error updating validation stats: {str(e)}")
    
    async def update_scanner_data(self):
        """Update scanner tab data"""
        try:
            # Get latest indicators
            indicators_data = await api_client.get_latest_indicators(50)
            if indicators_data and indicators_data.get("indicators"):
                ui_components.update_scanner_grid(indicators_data["indicators"])
                
        except Exception as e:
            console.error(f"Error updating scanner data: {str(e)}")
    
    async def update_trading_tab_data(self):
        """Update trading tab positions and trades data"""
        try:
            # Get active positions
            positions_data = await api_client.get_positions(active_only=True)
            if positions_data and positions_data.get("positions"):
                ui_components.update_positions_table(positions_data["positions"])
            
            # Get recent trades
            trades_data = await api_client.get_trades(limit=20)
            if trades_data and trades_data.get("trades"):
                ui_components.update_trades_table(trades_data["trades"])
                
        except Exception as e:
            console.error(f"Error updating trading tab data: {str(e)}")
    
    async def update_trading_data(self):
        """Update trading data table with real-time information"""
        try:
            trading_data = await api_client.get_trading_live_data()
            if trading_data:
                ui_components.update_trading_data_table(trading_data)
                console.log("Trading data table updated successfully")
            else:
                console.warn("No trading data received from API")
        except Exception as e:
            console.error(f"Error updating trading data: {str(e)}")
            ui_components.show_notification(
                "Erro Trading", 
                "Falha ao carregar dados de trading", 
                "error"
            )
    
    async def update_positions_data(self):
        """Update positions and trades tables"""
        try:
            # Update positions table
            positions_data = await api_client.get_positions()
            if positions_data:
                ui_components.update_positions_table(positions_data)
            
            # Update trades history table
            trades_data = await api_client.get_trades_history()
            if trades_data:
                ui_components.update_trades_table(trades_data)
                
        except Exception as e:
            console.error(f"Error updating positions data: {str(e)}")
    
    async def refresh_trading_data(self):
        """Manual refresh of trading data"""
        try:
            await self.update_trading_data()
            await self.update_positions_data()
            
            # Update last refresh timestamp
            current_time = datetime.now().strftime("%H:%M:%S")
            last_update_element = document.getElementById("trading-last-update")
            if last_update_element:
                last_update_element.textContent = f"Última atualização: {current_time}"
                
            ui_components.show_notification(
                "Trading", 
                "Dados de trading atualizados com sucesso", 
                "success"
            )
        except Exception as e:
            console.error(f"Error refreshing trading data: {str(e)}")
            ui_components.show_notification(
                "Erro", 
                "Falha ao atualizar dados de trading", 
                "error"
            )
    
    async def execute_auto_trade(self, symbol, signal_type, signal_data):
        """Execute automatic trade when signal is detected"""
        try:
            console.log(f"Executing auto trade: {signal_type} for {symbol}")
            
            trade_result = await api_client.execute_signal_trade(symbol, signal_type, signal_data)
            
            if trade_result and trade_result.get("success"):
                ui_components.show_notification(
                    "Trade Executado", 
                    f"{signal_type} executado para {symbol} em VST mode", 
                    "success"
                )
                
                # Refresh trading data to show new position
                await self.refresh_trading_data()
                
                return True
            else:
                error_msg = trade_result.get("error", "Erro desconhecido") if trade_result else "Resposta inválida"
                ui_components.show_notification(
                    "Erro no Trade", 
                    f"Falha ao executar {signal_type} para {symbol}: {error_msg}", 
                    "error"
                )
                return False
                
        except Exception as e:
            console.error(f"Error executing auto trade: {str(e)}")
            ui_components.show_notification(
                "Erro de Execução", 
                f"Erro ao executar trade para {symbol}: {str(e)}", 
                "error"
            )
            return False
    
    def filter_trading_data_table(self, filters):
        """Filter trading data table"""
        try:
            ui_components.filter_trading_data_table(filters)
            console.log("Trading data filtered successfully")
        except Exception as e:
            console.error(f"Error filtering trading data: {str(e)}")
    
    async def toggle_auto_trading(self, enable):
        """Toggle auto trading mode"""
        try:
            if enable:
                result = await api_client.start_auto_trading()
                if result and result.get("success"):
                    ui_components.show_notification(
                        "Auto Trading", 
                        "Auto Trading iniciado em VST mode", 
                        "success"
                    )
                    return True
            else:
                result = await api_client.stop_auto_trading()
                if result and result.get("success"):
                    ui_components.show_notification(
                        "Auto Trading", 
                        "Auto Trading parado", 
                        "warning"
                    )
                    return True
            
            return False
        except Exception as e:
            console.error(f"Error toggling auto trading: {str(e)}")
            ui_components.show_notification(
                "Erro", 
                f"Erro ao {'iniciar' if enable else 'parar'} auto trading", 
                "error"
            )
            return False
    
    def handle_realtime_update(self, data):
        """
        Handle real-time WebSocket updates with debounce to prevent data flickering.
        """
        console.log("Real-time update received...")
        try:
            # Só atualiza se não há uma atualização em progresso
            if not self.update_in_progress:
                console.log("Triggering debounced data refresh...")
                # Pequeno delay para evitar múltiplas atualizações simultâneas
                setTimeout = document.defaultView.setTimeout
                setTimeout(create_proxy(lambda: asyncio.create_task(self.debounced_update())), 1000)
            else:
                console.log("Update in progress, ignoring WebSocket update")
        except Exception as e:
            console.error(f"Error handling realtime update: {str(e)}")
    
    async def debounced_update(self):
        """Atualização com debounce para evitar conflitos"""
        try:
            await self.update_validation_table()
            await self.update_dashboard_summary()
        except Exception as e:
            console.error(f"Error in debounced update: {str(e)}")
    
    def handle_pong(self, data):
        """Handle WebSocket pong response"""
        # Keep connection alive - pong received
        pass
    
    def handle_scanner_message(self, data):
        """Handle scanner-related WebSocket messages with UI updates"""
        try:
            # Defensive check for data structure
            if not isinstance(data, dict):
                console.error(f"Expected dict, got {type(data)}: {data}")
                return
                
            message_type = data.get("type")
            payload = data.get("payload", {})
            
            if not message_type:
                console.error(f"No message type in data: {data}")
                return
                
        except Exception as e:
            console.error(f"Error parsing scanner message data: {e}")
            return
        
        if message_type == "scanner_progress":
            processed = payload.get("processed_count", 0)
            total = payload.get("total_assets", 0)
            progress_percent = payload.get("progress_percentage", 0)
            eta = payload.get("estimated_remaining_time_seconds", 0)
            message = payload.get("message", "Processando...")
            
            # Update scan progress UI elements if they exist
            try:
                progress_bar = document.getElementById("progress-bar")
                progress_percentage_elem = document.getElementById("progress-percentage")
                progress_subtitle = document.getElementById("progress-subtitle")
                progress_eta = document.getElementById("progress-eta")
                processed_count_elem = document.getElementById("processed-count")
                total_count_elem = document.getElementById("total-count")
                
                if progress_bar:
                    progress_bar.style.width = f"{progress_percent}%"
                if progress_percentage_elem:
                    progress_percentage_elem.textContent = f"{progress_percent:.1f}%"
                if progress_subtitle:
                    progress_subtitle.textContent = message
                if progress_eta and eta > 0:
                    minutes = int(eta // 60)
                    seconds = int(eta % 60)
                    eta_text = f"{minutes}m {seconds}s restantes" if minutes > 0 else f"{seconds}s restantes"
                    progress_eta.textContent = eta_text
                if processed_count_elem:
                    processed_count_elem.textContent = str(processed)
                if total_count_elem:
                    total_count_elem.textContent = str(total)
                    
                # Show progress details
                progress_details = document.getElementById("progress-details")
                if progress_details:
                    progress_details.style.display = "block"
                    
            except Exception as e:
                console.error(f"Error updating scanner progress UI: {e}")
            
            # Show notification for major progress milestones
            if processed % 100 == 0 or progress_percent >= 100:
                ui_components.show_notification(
                    "Scanner",
                    f"Processando: {processed}/{total} ({progress_percent:.1f}%)",
                    "info",
                    duration=2000
                )
            
        elif message_type == "scanner_completion":
            valid_assets = payload.get("valid_assets_count", 0)
            total_assets = payload.get("total_assets", 0)
            scan_duration = payload.get("scan_duration_seconds", 0)
            
            # Update final progress state
            try:
                progress_bar = document.getElementById("progress-bar")
                progress_percentage_elem = document.getElementById("progress-percentage")
                progress_subtitle = document.getElementById("progress-subtitle")
                valid_count_elem = document.getElementById("valid-count")
                
                if progress_bar:
                    progress_bar.style.width = "100%"
                if progress_percentage_elem:
                    progress_percentage_elem.textContent = "100%"
                if progress_subtitle:
                    progress_subtitle.textContent = "Scan concluído com sucesso!"
                if valid_count_elem:
                    valid_count_elem.textContent = str(valid_assets)
                    
            except Exception as e:
                console.error(f"Error updating scanner completion UI: {e}")
            
            ui_components.show_notification(
                "Scanner Concluído",
                f"Scan finalizado! {valid_assets}/{total_assets} ativos válidos em {scan_duration:.1f}s",
                "success",
                duration=5000
            )
            
            # Hide loading overlay after completion
            try:
                if js:
                    js.setTimeout(js.Function.fromString("() => { document.getElementById('loading-overlay').style.display = 'none'; }"), 2000)
            except:
                pass
                
            # Refresh validation table after completion
            asyncio.create_task(self.update_validation_table())
            
        elif message_type == "scanner_error":
            error_message = payload.get("message", "Erro desconhecido no scanner")
            
            # Update error state in UI
            try:
                progress_subtitle = document.getElementById("progress-subtitle")
                if progress_subtitle:
                    progress_subtitle.textContent = f"Erro: {error_message}"
            except Exception as e:
                console.error(f"Error updating scanner error UI: {e}")
                
            ui_components.show_notification(
                "Erro no Scanner",
                f"Ocorreu um erro durante o scan: {error_message}",
                "error",
                duration=8000
            )
            
            # Hide loading overlay on error
            try:
                if js:
                    js.setTimeout(js.Function.fromString("() => { document.getElementById('loading-overlay').style.display = 'none'; }"), 3000)
            except:
                pass

    def setup_auto_refresh(self):
        """Set up automatic data refresh"""
        # Clear any existing interval first
        if hasattr(self, 'update_interval') and self.update_interval:
            clearInterval(self.update_interval)
            
        def refresh_task():
            if self.auto_refresh_enabled and not getattr(self, 'update_in_progress', False):
                # Add safety check to prevent recursive calls
                try:
                    asyncio.create_task(self.refresh_current_tab())
                except Exception as e:
                    console.error(f"Error in refresh task: {e}")
        
        # Create interval for auto refresh
        self.update_interval = setInterval(
            create_proxy(refresh_task), 
            self.refresh_rate
        )
    
    async def refresh_current_tab(self):
        """Refresh data for current active tab with debounce"""
        # Prevent recursive calls with timestamp-based debounce
        try:
            current_time = js.Date.now()
        except NameError:
            # Fallback if js is not available
            import time
            current_time = int(time.time() * 1000)
        
        if hasattr(self, '_last_refresh_time') and (current_time - self._last_refresh_time) < 1000:
            console.log("Refresh called too soon, debouncing...")
            return
        
        # Evita refresh se há atualização em progresso
        if self.update_in_progress:
            console.log("Update in progress, skipping scheduled refresh")
            return
        
        # Set refresh timestamp to prevent recursion
        self._last_refresh_time = current_time
        
        try:
            console.log(f"Refreshing {self.current_tab} tab...")
            
            if self.current_tab == "scanner":
                await self.update_validation_table()
                await self.update_scanner_data()
            elif self.current_tab == "trading":
                await self.update_trading_data()
                await self.update_trading_tab_data()
            
            # Always update summary (but only if validation isn't updating)
            if not self.update_in_progress:
                await self.update_dashboard_summary()
            
        except Exception as e:
            console.error(f"Error refreshing {self.current_tab} tab: {str(e)}")
    
    def setup_event_listeners(self):
        """Set up DOM event listeners"""
        # Auto-refresh checkbox
        auto_refresh_checkbox = document.getElementById("auto-refresh")
        if auto_refresh_checkbox:
            def toggle_auto_refresh(event):
                self.auto_refresh_enabled = event.target.checked
                if self.auto_refresh_enabled:
                    ui_components.show_notification(
                        "Auto-refresh", 
                        "Atualização automática ativada", 
                        "info"
                    )
                else:
                    ui_components.show_notification(
                        "Auto-refresh", 
                        "Atualização automática desativada", 
                        "warning"
                    )
            
            auto_refresh_checkbox.addEventListener(
                "change", 
                create_proxy(toggle_auto_refresh)
            )
        
        # Tab switching
        tab_buttons = document.querySelectorAll(".tab-button")
        for button in tab_buttons:
            def on_tab_click(event):
                # Extract tab name from onclick attribute or data
                tab_name = event.target.textContent.strip()
                previous_tab = self.current_tab
                
                if "Scanner" in tab_name:
                    self.current_tab = "scanner"
                elif "Trading" in tab_name:
                    self.current_tab = "trading"
                elif "Analytics" in tab_name:
                    self.current_tab = "analytics"
                
                # Only refresh if tab actually changed and not in progress
                if self.current_tab != previous_tab and not getattr(self, 'update_in_progress', False):
                    try:
                        asyncio.create_task(self.refresh_current_tab())
                    except Exception as e:
                        console.error(f"Error refreshing tab: {e}")
            
            button.addEventListener("click", create_proxy(on_tab_click))
        
    
    def cleanup(self):
        """Cleanup resources"""
        if self.update_interval:
            clearInterval(self.update_interval)
        
        api_client.disconnect_websocket()


# Global functions for HTML onclick handlers
def refreshData():
    """Global function to refresh data manually"""
    asyncio.create_task(app.load_initial_data())

def closePosition(position_id):
    """Global function to close a position"""
    ui_components.show_notification(
        "Posição", 
        f"Fechamento de posição {position_id} solicitado", 
        "info"
    )
    # TODO: Implement position closing API call

def refreshValidationTable():
    """Global function to refresh validation table"""
    if app.update_in_progress:
        ui_components.show_notification(
            "Tabela", 
            "Atualização já em progresso, aguarde...", 
            "warning"
        )
        return
        
    asyncio.create_task(app.update_validation_table())
    ui_components.show_notification(
        "Tabela", 
        "Atualizando tabela de validação...", 
        "info"
    )

def exportTableData():
    """Global function to export table data"""
    ui_components.export_validation_table()
    ui_components.show_notification(
        "Export", 
        "Dados exportados para CSV", 
        "success"
    )

def sortTable(column):
    """Global function to sort table by column"""
    ui_components.sort_validation_table(column)

def previousPage():
    """Global function for table pagination"""
    ui_components.change_table_page(-1)

def nextPage():
    """Global function for table pagination"""
    ui_components.change_table_page(1)

async def check_revalidation_status():
    """Check the status of revalidation process"""
    status = await api_client.get_revalidation_status()
    if status and status.get("status"):
        status_data = status["status"]
        if status_data.get("running"):
            ui_components.show_notification(
                "Validação", 
                f"Processando... {status_data.get('progress', 0)}/{status_data.get('total', 0)} ativos", 
                "info"
            )
            # Check again in 2 seconds
            setTimeout = document.defaultView.setTimeout
            setTimeout(create_proxy(lambda: asyncio.create_task(check_revalidation_status())), 2000)
        elif status_data.get("completed"):
            ui_components.show_notification(
                "Validação", 
                f"Revalidação concluída! {status_data.get('total', 0)} ativos processados", 
                "success"
            )
            # Refresh the validation table
            asyncio.create_task(app.update_validation_table())
        elif status_data.get("error"):
            ui_components.show_notification(
                "Erro", 
                f"Erro na revalidação: {status_data.get('error')}", 
                "error"
            )

def forceRevalidation():
    """Global function to force asset revalidation with better feedback"""
    async def do_revalidation():
        try:
            ui_components.show_notification(
                "Validação", 
                "Enviando solicitação de revalidação...", 
                "info"
            )
            
            result = await api_client.force_revalidation()
            console.log(f"Revalidation result: {result}")
            
            if result is None:
                ui_components.show_notification(
                    "Erro de Validação",
                    "Falha ao iniciar revalidação: resposta da API nula.",
                    "error"
                )
                return

            if not result.get("error"):
                if result.get("status") == "already_running":
                    ui_components.show_notification(
                        "Validação", 
                        result.get("message", "Processo de revalidação já está em execução."), 
                        "warning"
                    )
                else:
                    ui_components.show_notification(
                        "Validação", 
                        result.get("message", "Revalidação iniciada com sucesso!"), 
                        "success"
                    )
                    # Start checking status
                    await check_revalidation_status()
            else:
                error_detail = result.get("detail", "Erro desconhecido")
                ui_components.show_notification(
                    "Erro de Validação", 
                    f"Falha ao iniciar revalidação: {error_detail}", 
                    "error"
                )

        except Exception as e:
            console.error(f"Error in revalidation: {e}")
            ui_components.show_notification(
                "Erro Crítico", 
                f"Erro inesperado na revalidação: {str(e)}", 
                "error"
            )
    
    asyncio.create_task(do_revalidation())


def filterValidationTable():
    """Global function to filter validation table"""
    ui_components.filter_validation_table()

def searchAssets(event):
    """Handle asset search with debouncing"""
    search_term = event.target.value.strip()
    
    # Clear previous timeout if exists
    from js import clearTimeout, setTimeout
    if hasattr(searchAssets, 'timeout'):
        clearTimeout(searchAssets.timeout)
    
    # Debounce search for 500ms
    def perform_search():
        console.log(f"Searching for: '{search_term}'")
        try:
            # Call the method on the global app instance
            asyncio.create_task(app.search_and_update_table(search_term))
        except NameError:
            console.error("Global app instance not available")
            ui_components.show_notification("Erro", "Sistema não inicializado", "error")
        except Exception as e:
            console.error(f"Search error: {e}")
            ui_components.show_notification("Erro de Pesquisa", f"Erro ao buscar: {e}", "error")
    
    searchAssets.timeout = setTimeout(create_proxy(perform_search), 500)

def clearSearch():
    """Clear search input and refresh table"""
    search_input = document.getElementById("symbol-search")
    if search_input:
        search_input.value = ""
        try:
            asyncio.create_task(app.search_and_update_table("", 1))
        except NameError:
            console.error("Global app instance not available for clearSearch")
            ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def sortValidationTableServer(column, direction):
    """Global function for server-side sorting"""
    try:
        asyncio.create_task(app.sort_validation_table_server(column, direction))
    except NameError:
        console.error("Global app instance not available for sorting")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def refreshValidationTablePage(page):
    """Global function to refresh specific page"""
    try:
        asyncio.create_task(app.refresh_validation_table_page(page))
    except NameError:
        console.error("Global app instance not available for pagination")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def applyValidationTableFilters(filters):
    """Global function to apply filters"""
    try:
        asyncio.create_task(app.apply_validation_table_filters(filters))
    except NameError:
        console.error("Global app instance not available for filters")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

# Trading Tab Global Functions
def updateTradingDataTable(trading_data):
    """Global function to update trading data table"""
    try:
        ui_components.update_trading_data_table(trading_data)
    except Exception as e:
        console.error(f"Error updating trading data table: {e}")
        ui_components.show_notification("Erro", "Falha ao atualizar tabela de trading", "error")

def filterTradingDataTable(filters):
    """Global function to filter trading data table"""
    try:
        app.filter_trading_data_table(filters)
    except NameError:
        console.error("Global app instance not available for trading filters")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def refreshTradingData():
    """Global function to refresh trading data"""
    try:
        asyncio.create_task(app.refresh_trading_data())
    except NameError:
        console.error("Global app instance not available for trading refresh")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def executeSignalTrade(symbol, signal_type, signal_data):
    """Global function to execute signal trade"""
    try:
        asyncio.create_task(app.execute_auto_trade(symbol, signal_type, signal_data))
    except NameError:
        console.error("Global app instance not available for trade execution")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

# Removed toggleAutoTrading function to avoid conflicts with JavaScript version

# Initialize the application first (with singleton protection)
if 'app' not in globals() or app is None:
    app = TradingBotApp()
    console.log("Trading bot app instance created")
else:
    console.log("Trading bot app already exists, reusing instance")

# Make functions globally available
document.refreshData = create_proxy(refreshData)
document.refreshValidationTable = create_proxy(refreshValidationTable)
document.exportTableData = create_proxy(exportTableData)
document.sortTable = create_proxy(sortTable)
document.previousPage = create_proxy(previousPage)
document.nextPage = create_proxy(nextPage)
document.closePosition = create_proxy(closePosition)
document.forceRevalidation = create_proxy(forceRevalidation)
document.filterValidationTable = create_proxy(filterValidationTable)
document.searchAssets = create_proxy(searchAssets)
document.clearSearch = create_proxy(clearSearch)
document.showNotification = create_proxy(ui_components.show_notification)

# New server-side functions
document.sortValidationTableServer = create_proxy(sortValidationTableServer)
document.refreshValidationTablePage = create_proxy(refreshValidationTablePage)
document.applyValidationTableFilters = create_proxy(applyValidationTableFilters)

# Trading functions
document.updateTradingDataTable = create_proxy(updateTradingDataTable)
document.filterTradingDataTable = create_proxy(filterTradingDataTable)
document.refreshTradingData = create_proxy(refreshTradingData)
document.executeSignalTrade = create_proxy(executeSignalTrade)
# Removed toggleAutoTrading from document proxy to avoid conflicts

# Also make all functions available on window object for JavaScript compatibility
window.showNotification = create_proxy(ui_components.show_notification)
window.forceRevalidation = create_proxy(forceRevalidation)
window.refreshValidationTable = create_proxy(refreshValidationTable)
window.exportTableData = create_proxy(exportTableData)
window.sortTable = create_proxy(sortTable)
window.previousPage = create_proxy(previousPage)
window.nextPage = create_proxy(nextPage)
window.clearSearch = create_proxy(clearSearch)
window.searchAssets = create_proxy(searchAssets)

# Trading functions on window
window.updateTradingDataTable = create_proxy(updateTradingDataTable)
window.filterTradingDataTable = create_proxy(filterTradingDataTable)
window.refreshTradingData = create_proxy(refreshTradingData)
window.executeSignalTrade = create_proxy(executeSignalTrade)
window.handleScannerMessage = create_proxy(app.handle_scanner_message)
# Removed toggleAutoTrading from window proxy to avoid conflicts

# Global function to handle scanner WebSocket messages from JavaScript
def handleScannerWebSocketMessage(data):
    """Global function to handle scanner messages from JavaScript WebSocket"""
    try:
        # Debug logging to understand the data structure
        console.log(f"Handling scanner WebSocket message: {type(data)}")
        console.log(f"Data content: {data}")
        
        # Ensure data is properly formatted
        if isinstance(data, str):
            import json
            try:
                data = json.loads(data)
            except json.JSONDecodeError as json_err:
                console.error(f"Failed to parse JSON data: {json_err}")
                return
        
        app.handle_scanner_message(data)
    except Exception as e:
        console.error(f"Error handling scanner WebSocket message: {e}")
        console.error(f"Error type: {type(e)}")
        console.error(f"Data type: {type(data)}, Data: {data}")

window.handleScannerWebSocketMessage = create_proxy(handleScannerWebSocketMessage)

console.log("BingX Trading Bot Dashboard loaded successfully!")