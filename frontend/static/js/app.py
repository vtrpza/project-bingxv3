"""
Main PyScript Application for BingX Trading Bot Dashboard
Coordinates all frontend functionality and real-time updates
"""

import asyncio
import json
from datetime import datetime, timedelta
from js import document, console, setInterval, clearInterval, setTimeout, window
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
        """Load initial dashboard data"""
        try:
            document.getElementById("loading-overlay").style.display = "flex"
            
            # Load dashboard summary
            await self.update_dashboard_summary()
            
            # Load validation table
            await self.update_validation_table()
            
            # Load scanner data
            await self.update_scanner_data()
            
            # Load trading data
            await self.update_trading_data()
            
            ui_components.show_notification(
                "Dashboard", 
                "Dados carregados com sucesso", 
                "success"
            )
            
        except Exception as e:
            console.error(f"Error loading initial data: {str(e)}")
            ui_components.show_notification(
                "Erro", 
                "Falha ao carregar dados iniciais", 
                "error"
            )
        finally:
            document.getElementById("loading-overlay").style.display = "none"
    
    async def update_dashboard_summary(self):
        """Update dashboard summary statistics"""
        try:
            summary_data = await api_client.get_dashboard_summary()
            if summary_data:
                ui_components.update_stats_cards(summary_data)
        except Exception as e:
            console.error(f"Error updating dashboard summary: {str(e)}")
    
    async def update_validation_table(self, page=1):
        """Update asset validation table with server-side pagination"""
        # Evita atualizações simultâneas
        if self.update_in_progress:
            console.log("Validation table update already in progress, skipping...")
            return
            
        try:
            self.update_in_progress = True
            console.log(f"Updating validation table page {page}...")
            
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
    
    async def search_and_update_table(self, search_term="", page=1):
        """Search and update validation table with server-side pagination"""
        try:
            console.log(f"Performing search for: '{search_term}' on page {page}")
            
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
        """Sort validation table using server-side sorting"""
        try:
            console.log(f"Server-side sorting: {column} {direction}")
            
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
            
            current_sort = getattr(ui_components.UIComponents, '_current_sort', {'column': 'symbol', 'direction': 'asc'})
            
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
        """Apply filters to validation table"""
        try:
            console.log(f"Applying filters: {filters}")
            
            # Get current search and sort
            search_input = document.getElementById("symbol-search")
            search_term = search_input.value.strip() if search_input else ""
            
            current_sort = getattr(ui_components.UIComponents, '_current_sort', {'column': 'symbol', 'direction': 'asc'})
            
            # Get filtered data from API
            validation_data = await api_client.get_validation_table(
                page=1,  # Reset to first page on filter
                per_page=25,
                sort_by=current_sort.get('column', 'symbol'),
                sort_direction=current_sort.get('direction', 'asc'),
                filter_valid_only=filters.get('filter_valid_only', False),
                include_invalid=not filters.get('filter_valid_only', False),
                search=search_term if search_term else None
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
    
    async def update_trading_data(self):
        """Update trading tab data"""
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
            console.error(f"Error updating trading data: {str(e)}")
    
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
    
    def setup_auto_refresh(self):
        """Set up automatic data refresh"""
        def refresh_task():
            if self.auto_refresh_enabled:
                asyncio.create_task(self.refresh_current_tab())
        
        # Create interval for auto refresh
        self.update_interval = setInterval(
            create_proxy(refresh_task), 
            self.refresh_rate
        )
    
    async def refresh_current_tab(self):
        """Refresh data for current active tab with debounce"""
        # Evita refresh se há atualização em progresso
        if self.update_in_progress:
            console.log("Update in progress, skipping scheduled refresh")
            return
            
        try:
            console.log(f"Refreshing {self.current_tab} tab...")
            
            if self.current_tab == "scanner":
                await self.update_validation_table()
                await self.update_scanner_data()
            elif self.current_tab == "trading":
                await self.update_trading_data()
            
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
                if "Scanner" in tab_name:
                    self.current_tab = "scanner"
                elif "Trading" in tab_name:
                    self.current_tab = "trading"
                elif "Analytics" in tab_name:
                    self.current_tab = "analytics"
                
                # Refresh data for new tab
                asyncio.create_task(self.refresh_current_tab())
            
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
            asyncio.create_task(app.search_and_update_table(search_term))
        except Exception as e:
            console.error(f"Search error: {e}")
            # Fallback: show error notification
            if hasattr(window, 'showNotification'):
                window.showNotification("Erro de Pesquisa", f"Erro ao buscar: {e}", "error")
    
    searchAssets.timeout = setTimeout(create_proxy(perform_search), 500)

def clearSearch():
    """Clear search input and refresh table"""
    search_input = document.getElementById("symbol-search")
    if search_input:
        search_input.value = ""
        asyncio.create_task(app.search_and_update_table("", 1))

def sortValidationTableServer(column, direction):
    """Global function for server-side sorting"""
    asyncio.create_task(app.sort_validation_table_server(column, direction))

def refreshValidationTablePage(page):
    """Global function to refresh specific page"""
    asyncio.create_task(app.refresh_validation_table_page(page))

def applyValidationTableFilters(filters):
    """Global function to apply filters"""
    asyncio.create_task(app.apply_validation_table_filters(filters))

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

# Also make showNotification available on window object for JavaScript compatibility
window.showNotification = create_proxy(ui_components.show_notification)

# Initialize the application
app = TradingBotApp()

console.log("BingX Trading Bot Dashboard loaded successfully!")